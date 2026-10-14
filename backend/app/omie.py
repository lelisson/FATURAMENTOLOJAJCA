"""Cliente Omie (somente leitura) — NF-e + NFC-e (PDV) para o painel de vendas."""
from __future__ import annotations

import html
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from . import transform as T

READ_ONLY_CALLS = frozenset(
    {
        "ListarNF",
        "ConsultarNF",
        "StatusAplicativo",
        "CuponsFiscais",
        "ConsultarPedido",
        "ListarPosEstoque",
    }
)

BASE = os.getenv("OMIE_BASE_URL", "https://app.omie.com.br/api/v1").rstrip("/")
EP_NF = "/produtos/nfconsultar/"
EP_CUPOM = "/produtos/cupomfiscalconsultar/"
EP_PEDIDO = "/produtos/pedido/"
EP_ESTOQUE = "/estoque/consulta/"

# Operações que não entram no faturamento de vendas (remessa etc.)
OP_EXCLUIDAS = frozenset({"14", "16", "24", "04"})

POR_PAGINA_NF = 50
POR_PAGINA_CUPOM = 100


def _credenciais() -> tuple[str, str]:
    k = (os.getenv("OMIE_APP_KEY") or "").strip()
    s = (os.getenv("OMIE_APP_SECRET") or "").strip()
    if not k or not s:
        raise RuntimeError("OMIE_APP_KEY e OMIE_APP_SECRET não configurados no .env")
    return k, s


class OmieBloqueada(RuntimeError):
    """A Omie bloqueou o método por consumo indevido; insistir só prolonga o bloqueio."""


_bloqueado_ate: dict[str, float] = {}

# IPv4: em redes sem rota IPv6 a conexão fica pendurada até o timeout em cada tentativa.
_http = httpx.Client(transport=httpx.HTTPTransport(local_address="0.0.0.0"),
                     timeout=httpx.Timeout(120, connect=15))


def _post(call: str, endpoint: str, param: dict, tentativas: int = 3) -> dict:
    if call not in READ_ONLY_CALLS:
        raise PermissionError(f"Método Omie não permitido (somente leitura): {call}")
    if time.time() < _bloqueado_ate.get(call, 0):
        raise OmieBloqueada(f"Omie ({call}) bloqueada até {time.strftime('%H:%M', time.localtime(_bloqueado_ate[call]))}")
    app_key, app_secret = _credenciais()
    corpo = {
        "call": call,
        "app_key": app_key,
        "app_secret": app_secret,
        "param": [param],
    }
    url = BASE + endpoint
    for i in range(tentativas):
        try:
            r = _http.post(url, json=corpo)
        except httpx.HTTPError:
            if i == tentativas - 1:
                raise
            time.sleep(3 * (i + 1))
            continue
        try:
            data = r.json()
        except ValueError:
            data = {}
        falha = data.get("faultstring") if isinstance(data, dict) else None
        if r.status_code == 425 or "MISUSE" in str(data.get("faultcode", "") if isinstance(data, dict) else ""):
            m = re.search(r"(\d+)\s*segundos", falha or "")
            _bloqueado_ate[call] = time.time() + (int(m.group(1)) if m else 900)
            raise OmieBloqueada(f"Omie ({call}): {falha}")
        if falha:
            raise RuntimeError(f"Omie ({call}): {falha}")
        if r.status_code in (429, 502, 503, 504) and i < tentativas - 1:
            time.sleep(3 * (i + 1))
            continue
        r.raise_for_status()
        return data
    raise RuntimeError(f"Falha ao chamar a API Omie ({call})")


def _br(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}"


def _iso_br(d: str) -> str:
    d = (d or "").strip()
    if not d:
        return ""
    if re.match(r"^\d{4}-\d{2}-\d{2}$", d):
        return d
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", d)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return d


def _f(val) -> float:
    if val is None or val == "":
        return 0.0
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def _sim(val) -> bool:
    return str(val or "").strip().upper() in ("S", "SIM", "1", "TRUE", "Y")


def _texto(s: str) -> str:
    return html.unescape((s or "").strip())


CACHE_PEDIDOS = Path(__file__).resolve().parents[1] / "data" / "cache_pedidos.json"


def _consultar_consumidor(id_pedido: int) -> bool:
    resp = _post("ConsultarPedido", EP_PEDIDO, {"codigo_pedido": id_pedido})
    ped = resp.get("pedido_venda_produto") or {}
    inf = ped.get("informacoes_adicionais") or {}
    return _sim(inf.get("consumidor_final"))


class _CachePedidos:
    """consumidor_final vem de ConsultarPedido → informacoes_adicionais; persistido em disco."""

    def __init__(self) -> None:
        self._consumidor: dict[int, bool] = {}
        if CACHE_PEDIDOS.exists():
            try:
                raw = json.loads(CACHE_PEDIDOS.read_text(encoding="utf-8"))
                self._consumidor = {int(k): bool(v) for k, v in raw.items()}
            except (ValueError, OSError):
                self._consumidor = {}

    def carregar(self, ids: set[int]) -> None:
        faltam = [i for i in ids if i and i not in self._consumidor]
        if not faltam:
            return
        # Sequencial: ConsultarPedido em paralelo/repetido faz a Omie bloquear o método.
        for i in faltam:
            try:
                self._consumidor[i] = _consultar_consumidor(i)
            except OmieBloqueada:
                break
            except RuntimeError:
                continue
            time.sleep(0.3)
        CACHE_PEDIDOS.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PEDIDOS.write_text(
            json.dumps({str(k): v for k, v in self._consumidor.items()}), encoding="utf-8"
        )

    def consumidor_final(self, id_pedido: int) -> bool:
        return self._consumidor.get(id_pedido, False)


def _cancelada_nf(nf: dict) -> bool:
    ide = nf.get("ide") or {}
    if (ide.get("dCan") or "").strip():
        return True
    if (ide.get("dInut") or "").strip():
        return True
    if _sim(ide.get("cDeneg")):
        return True
    return False


def _codigo_operacao(nf: dict) -> str:
    ped = nf.get("pedido") or {}
    compl = nf.get("compl") or {}
    for chave in ("codigo_operacao", "cCodOperacao", "opPedido", "cOpPedido"):
        v = ped.get(chave) or compl.get(chave)
        if v is not None and str(v).strip() != "":
            return str(v).strip()
    return ""


def _cliente_nf(nf: dict) -> str:
    dest = nf.get("nfDestInt") or {}
    return _texto(dest.get("cRazao") or dest.get("cNome") or "")


def _paginar(call: str, endpoint: str, param, lista: str, total_paginas: str) -> list[dict]:
    """Busca a página 1 e as demais em paralelo (máx. 4 simultâneas por método no Omie)."""
    primeira = _post(call, endpoint, param(1))
    out = list(primeira.get(lista) or [])
    total = int(primeira.get(total_paginas) or 1)
    if total > 1:
        with ThreadPoolExecutor(max_workers=4) as ex:
            for resp in ex.map(lambda p: _post(call, endpoint, param(p)), range(2, total + 1)):
                out.extend(resp.get(lista) or [])
    return out


def listar_nf_bruto(inicio: str, fim: str) -> list[dict]:
    return _paginar(
        "ListarNF",
        EP_NF,
        lambda p: {
            "pagina": p,
            "registros_por_pagina": POR_PAGINA_NF,
            "apenas_importado_api": "N",
            "cDetalhesPedido": "S",
            "dEmiInicial": _br(inicio),
            "dEmiFinal": _br(fim),
            "tpNF": "1",
        },
        "nfCadastro",
        "total_de_paginas",
    )


def listar_cupons_bruto(inicio: str, fim: str) -> list[dict]:
    return _paginar(
        "CuponsFiscais",
        EP_CUPOM,
        lambda p: {
            "nPagina": p,
            "nRegPorPagina": POR_PAGINA_CUPOM,
            "dDtEmissaoDe": _br(inicio),
            "dDtEmissaoAte": _br(fim),
        },
        "cupons",
        "nTotPaginas",
    )


def mapear_nf(nf: dict, pedidos: _CachePedidos) -> list[dict]:
    if _cancelada_nf(nf):
        return []
    op = _codigo_operacao(nf)
    if op in OP_EXCLUIDAS:
        return []
    ped = nf.get("pedido") or {}
    if _sim(ped.get("cCancelado")) or _sim(ped.get("cDevolvido")):
        return []

    ide = nf.get("ide") or {}
    data_iso = _iso_br(str(ide.get("dEmi") or ""))
    if not data_iso:
        return []

    id_ped = int((nf.get("compl") or {}).get("nIdPedido") or 0)
    consumo = pedidos.consumidor_final(id_ped)
    nf_num = ide.get("nNF") or ide.get("nDoc") or "0"
    cliente = _cliente_nf(nf)

    linhas: list[dict] = []
    for det in nf.get("det") or []:
        pr = det.get("prod") or {}
        produto = _texto(pr.get("xProd") or pr.get("cProd") or "")
        if not produto:
            continue
        # vTotItem do Omie vem bruto (sem abater vDesc); o relatório de faturamento usa o líquido
        valor = (
            _f(pr.get("vProd")) - _f(pr.get("vDesc"))
            + _f(pr.get("vFrete")) + _f(pr.get("vSeg")) + _f(pr.get("vOutro"))
        )
        if valor <= 0:
            continue
        linhas.append(
            T.linha(data_iso, nf_num, "Ped", cliente, produto, valor, False, consumo, pr.get("cProd"))
        )
    return linhas


def mapear_cupom(cupom: dict) -> list[dict]:
    cab = cupom.get("cabecalhoCupom") or {}
    data_iso = _iso_br(str(cab.get("dDtEmissaoCupom") or ""))
    if not data_iso:
        return []
    nf_num = cab.get("nNumCupom") or "0"

    linhas: list[dict] = []
    for item in cupom.get("itensCupom") or []:
        if _sim(item.get("cCupomCancelado")) or _sim(item.get("cItemCancelado")):
            continue
        produto = _texto(item.get("xProd") or item.get("cCodigo") or "")
        if not produto:
            continue
        valor = _f(item.get("vItem"))
        if valor <= 0:
            valor = _f(item.get("vUnit")) * _f(item.get("nQuant")) - _f(item.get("vDesc")) + _f(item.get("vAcresc"))
        if valor <= 0:
            continue
        linhas.append(
            T.linha(data_iso, nf_num, "Ven", "", produto, valor, True, False, item.get("cCodigo"))
        )
    return linhas


def vendas(inicio: str, fim: str) -> list[dict]:
    pedidos = _CachePedidos()
    with ThreadPoolExecutor(max_workers=2) as ex:
        f_nf = ex.submit(listar_nf_bruto, inicio, fim)
        f_cup = ex.submit(listar_cupons_bruto, inicio, fim)
        nfs, cupons = f_nf.result(), f_cup.result()
    pedidos.carregar({int((nf.get("compl") or {}).get("nIdPedido") or 0) for nf in nfs})
    out: list[dict] = []
    for nf in nfs:
        out.extend(mapear_nf(nf, pedidos))
    for cupom in cupons:
        out.extend(mapear_cupom(cupom))
    return out


def estoque_atual() -> list[dict]:
    """Produtos com saldo positivo hoje (todos os locais da filial), a custo médio."""
    hoje = time.strftime("%Y-%m-%d")
    itens = _paginar(
        "ListarPosEstoque",
        EP_ESTOQUE,
        lambda p: {"nPagina": p, "nRegPorPagina": 100, "dDataPosicao": _br(hoje), "cExibeTodos": "N"},
        "produtos",
        "nTotPaginas",
    )
    por_produto: dict[str, dict] = {}
    for it in itens:
        saldo = _f(it.get("nSaldo") if it.get("nSaldo") is not None else it.get("fisico"))
        if saldo <= 0:
            continue
        cod = str(it.get("cCodigo") or it.get("nCodProd") or "").strip()
        p = T.normaliza_produto(_texto(it.get("cDescricao") or ""))
        reg = por_produto.setdefault(cod, {"cod": cod, "p": p, "f": T.familia(p), "q": 0.0, "custo": 0.0,
                                           "preco": _f(it.get("nPrecoUnitario"))})
        reg["q"] += saldo
        reg["custo"] += saldo * _f(it.get("nCMC"))
    for reg in por_produto.values():
        reg["q"] = round(reg["q"], 3)
        reg["custo"] = round(reg["custo"], 2)
    return list(por_produto.values())


def testar_conexao() -> str:
    hoje = time.strftime("%Y-%m-%d")
    _post(
        "ListarNF",
        EP_NF,
        {
            "pagina": 1,
            "registros_por_pagina": 1,
            "dEmiInicial": _br(hoje),
            "dEmiFinal": _br(hoje),
            "tpNF": "1",
        },
    )
    _post(
        "CuponsFiscais",
        EP_CUPOM,
        {"nPagina": 1, "nRegPorPagina": 1, "dDtEmissaoDe": _br(hoje), "dDtEmissaoAte": _br(hoje)},
    )
    return "Conexão Omie OK (NF-e + NFC-e PDV, somente leitura)."
