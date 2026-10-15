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

from . import ambiente
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

# Itens de NF de saída que não são venda: transferências, devoluções (de transferência ou de compra),
# bonificação/brinde, amostra grátis e outras saídas
CFOP_SAIDA_NAO_VENDA = frozenset({
    "5151", "5152", "5155", "5156", "6151", "6152", "6155", "6156",
    "5201", "5202", "5208", "5209", "5210", "5410", "5411", "5409",
    "6201", "6202", "6208", "6209", "6210", "6410", "6411", "6409",
    "5910", "5911", "5949", "6910", "6911", "6949",
})
# NF de entrada de devolução de venda: abate o faturamento na data da devolução
CFOP_DEVOLUCAO_VENDA = frozenset({"1201", "1202", "1410", "1411", "2201", "2202", "2410", "2411"})

POR_PAGINA_NF = 50
POR_PAGINA_CUPOM = 100


# Empresa ativa → chaves OMIE_FILIAL_APP_KEY / OMIE_MATRIZ_APP_KEY. As chamadas de uma empresa rodam
# em sequência (publicar_dados.py), então um global basta, inclusive nas threads de _paginar.
EMPRESAS = ("filial", "matriz")
_empresa = "filial"


def usar_empresa(empresa: str) -> None:
    global _empresa
    if empresa not in EMPRESAS:
        raise ValueError(empresa)
    _empresa = empresa


def carregar_chaves_matriz_local() -> None:
    """No PC, as chaves da matriz são OMIE_APP_KEY/OMIE_APP_SECRET do usuário do Windows (as mesmas dos
    scripts de estoque); no GitHub Actions já vêm como OMIE_MATRIZ_*."""
    if ambiente.ler("OMIE_MATRIZ_APP_KEY"):
        return
    k, s = ambiente.ler("OMIE_APP_KEY"), ambiente.ler("OMIE_APP_SECRET")
    if k and s:
        os.environ["OMIE_MATRIZ_APP_KEY"], os.environ["OMIE_MATRIZ_APP_SECRET"] = k, s


def _credenciais() -> tuple[str, str]:
    pre = f"OMIE_{_empresa.upper()}_"
    k, s = ambiente.ler(pre + "APP_KEY"), ambiente.ler(pre + "APP_SECRET")
    if not k or not s:
        raise RuntimeError(f"{pre}APP_KEY e {pre}APP_SECRET não configurados")
    return k, s


class OmieBloqueada(RuntimeError):
    """A Omie bloqueou o método por consumo indevido; insistir só prolonga o bloqueio."""


_bloqueado_ate: dict[str, float] = {}

# IPv4: em redes sem rota IPv6 a conexão fica pendurada até o timeout em cada tentativa.
_http = httpx.Client(transport=httpx.HTTPTransport(local_address="0.0.0.0"),
                     timeout=httpx.Timeout(120, connect=15))


def _post(call: str, endpoint: str, param: dict, tentativas: int = 6) -> dict:
    if call not in READ_ONLY_CALLS:
        raise PermissionError(f"Método Omie não permitido (somente leitura): {call}")
    trava = f"{_empresa}:{call}"
    if time.time() < _bloqueado_ate.get(trava, 0):
        raise OmieBloqueada(f"Omie ({call}) bloqueada até {time.strftime('%H:%M', time.localtime(_bloqueado_ate[trava]))}")
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
            _bloqueado_ate[trava] = time.time() + (int(m.group(1)) if m else 900)
            raise OmieBloqueada(f"Omie ({call}): {falha}")
        if falha:
            # o mesmo método ainda em processamento na Omie (comum no ListarPosEstoque): aguarda e repete
            if ("requisição desse método sendo executada" in falha or "REDUNDANT" in falha) and i < tentativas - 1:
                m = re.search(r"(\d+)\s*segundos", falha)
                time.sleep(int(m.group(1)) + 1 if m else 5 * (i + 1))
                continue
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


PASTA_DADOS = Path(__file__).resolve().parents[1] / "data"


def _arquivo_cache_pedidos() -> Path:
    return PASTA_DADOS / ("cache_pedidos.json" if _empresa == "filial" else f"cache_pedidos_{_empresa}.json")


def _consultar_consumidor(id_pedido: int) -> bool:
    resp = _post("ConsultarPedido", EP_PEDIDO, {"codigo_pedido": id_pedido})
    ped = resp.get("pedido_venda_produto") or {}
    inf = ped.get("informacoes_adicionais") or {}
    return _sim(inf.get("consumidor_final"))


class _CachePedidos:
    """consumidor_final vem de ConsultarPedido → informacoes_adicionais; persistido em disco."""

    def __init__(self) -> None:
        self._consumidor: dict[int, bool] = {}
        self._arquivo = _arquivo_cache_pedidos()
        if self._arquivo.exists():
            try:
                raw = json.loads(self._arquivo.read_text(encoding="utf-8"))
                self._consumidor = {int(k): bool(v) for k, v in raw.items()}
            except (ValueError, OSError):
                self._consumidor = {}

    def carregar(self, ids: set[int]) -> None:
        faltam = [i for i in ids if i and i not in self._consumidor]
        if not faltam:
            return
        # Sequencial: ConsultarPedido em paralelo/repetido faz a Omie bloquear o método.
        # PEDIDOS_MAX_SEG limita o tempo por execução; o que faltar é consultado nas próximas.
        limite = time.time() + float(os.getenv("PEDIDOS_MAX_SEG") or "inf")
        for i in faltam:
            if time.time() > limite:
                break
            try:
                self._consumidor[i] = _consultar_consumidor(i)
            except OmieBloqueada:
                break
            except RuntimeError:
                continue
            time.sleep(0.3)
        self._arquivo.parent.mkdir(parents=True, exist_ok=True)
        self._arquivo.write_text(
            json.dumps({str(k): v for k, v in self._consumidor.items()}), encoding="utf-8"
        )

    def consumidor_final(self, id_pedido: int) -> bool:
        return self._consumidor.get(id_pedido, False)

    def conhecido(self, id_pedido: int) -> bool:
        return not id_pedido or id_pedido in self._consumidor


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


def _paginar(call: str, endpoint: str, param, lista: str, total_paginas: str, paralelo: int = 4) -> list[dict]:
    """Busca a página 1 e as demais em paralelo (máx. 4 simultâneas por método no Omie)."""
    primeira = _post(call, endpoint, param(1))
    out = list(primeira.get(lista) or [])
    total = int(primeira.get(total_paginas) or 1)
    if total > 1:
        with ThreadPoolExecutor(max_workers=paralelo) as ex:
            for resp in ex.map(lambda p: _post(call, endpoint, param(p)), range(2, total + 1)):
                out.extend(resp.get(lista) or [])
    return out


def _cfop(pr: dict) -> str:
    return re.sub(r"\D", "", str(pr.get("CFOP") or ""))


def _valor_item(pr: dict) -> float:
    # vTotItem do Omie vem bruto (sem abater vDesc); o relatório de faturamento usa o líquido
    return (
        _f(pr.get("vProd")) - _f(pr.get("vDesc"))
        + _f(pr.get("vFrete")) + _f(pr.get("vSeg")) + _f(pr.get("vOutro"))
    )


def listar_nf_bruto(inicio: str, fim: str, tp_nf: str = "1") -> list[dict]:
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
            "tpNF": tp_nf,
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


def _nf_de_venda(nf: dict) -> bool:
    # Pedido devolvido continua como venda no mês dele; a NF de devolução abate no mês da devolução.
    return not (_cancelada_nf(nf) or _codigo_operacao(nf) in OP_EXCLUIDAS
                or _sim((nf.get("pedido") or {}).get("cCancelado")))


def mapear_nf(nf: dict, pedidos: _CachePedidos) -> list[dict]:
    if not _nf_de_venda(nf):
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
        if not produto or _cfop(pr) in CFOP_SAIDA_NAO_VENDA:
            continue
        valor = _valor_item(pr)
        if valor <= 0:
            continue
        linhas.append(
            T.linha(data_iso, nf_num, "Ped", cliente, produto, valor, False, consumo, pr.get("cProd"))
        )
    return linhas


def mapear_devolucao(nf: dict, canal_cliente: dict[str, tuple[bool, bool]]) -> list[dict]:
    """Itens de devolução de venda viram linhas negativas na data de emissão da NF de devolução."""
    if _cancelada_nf(nf):
        return []
    ide = nf.get("ide") or {}
    data_iso = _iso_br(str(ide.get("dEmi") or ""))
    if not data_iso:
        return []
    nf_num = ide.get("nNF") or "0"
    cliente = _cliente_nf(nf)
    # Matriz não tem PDV: sem canal conhecido, assume pedido (não balcão).
    padrao_pdv = _empresa == "filial" and not cliente
    is_pdv, consumo = canal_cliente.get(cliente or T.ANON, (padrao_pdv, False))

    linhas: list[dict] = []
    for det in nf.get("det") or []:
        pr = det.get("prod") or {}
        if _cfop(pr) not in CFOP_DEVOLUCAO_VENDA:
            continue
        produto = _texto(pr.get("xProd") or pr.get("cProd") or "")
        valor = _valor_item(pr)
        if not produto or valor <= 0:
            continue
        r = T.linha(data_iso, nf_num, "Dev", cliente, produto, -valor, is_pdv, consumo, pr.get("cProd"))
        r["dv"] = 1
        linhas.append(r)
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


def _coletar(inicio: str, fim: str, anteriores: list[dict] = ()) -> tuple[list[dict], set[str]]:
    """Linhas do período e os meses (AAAA-MM) com pedidos cujo consumidor_final ainda não foi consultado.

    `anteriores` são linhas já conhecidas de antes de `inicio`, usadas só para o canal das devoluções."""
    pedidos = _CachePedidos()
    # Saídas e entradas em sequência: ListarNF aceita no máximo 4 chamadas simultâneas.
    def _nfs() -> tuple[list[dict], list[dict]]:
        return listar_nf_bruto(inicio, fim, "1"), listar_nf_bruto(inicio, fim, "0")

    with ThreadPoolExecutor(max_workers=2) as ex:
        f_nf = ex.submit(_nfs)
        # Matriz não tem PDV / CuponsFiscais.
        f_cup = ex.submit(listar_cupons_bruto, inicio, fim) if _empresa == "filial" else None
        (nfs, entradas) = f_nf.result()
        cupons = f_cup.result() if f_cup else []

    def _id_ped(nf: dict) -> int:
        return int((nf.get("compl") or {}).get("nIdPedido") or 0)

    nfs = [nf for nf in nfs if _nf_de_venda(nf)]
    pedidos.carregar({_id_ped(nf) for nf in nfs})
    pendentes = {_iso_br(str((nf.get("ide") or {}).get("dEmi") or ""))[:7]
                 for nf in nfs if not pedidos.conhecido(_id_ped(nf))}
    out: list[dict] = []
    for nf in nfs:
        out.extend(mapear_nf(nf, pedidos))
    for cupom in cupons:
        out.extend(mapear_cupom(cupom))
    canal_cliente = {r["c"]: (r["ch"] == "PDV", r["ch"] == "Pedido – consumo final")
                     for r in sorted([*anteriores, *out], key=lambda r: r["d"]) if not r.get("dv")}
    for nf in entradas:
        out.extend(mapear_devolucao(nf, canal_cliente))
    return out, pendentes


def vendas(inicio: str, fim: str) -> list[dict]:
    return _coletar(inicio, fim)[0]


def _proximo_mes(mes: str) -> str:
    a, m = int(mes[:4]), int(mes[5:7])
    return f"{a + m // 12}-{m % 12 + 1:02d}"


def vendas_congelando(inicio: str, fim: str, congelado: dict[str, list[dict]],
                      fechado_ate: str) -> tuple[list[dict], dict[str, list[dict]]]:
    """Como vendas(), mas sem consultar de novo os meses já em `congelado` (AAAA-MM → linhas).

    Devolve as linhas e o novo `congelado`: meses anteriores a `fechado_ate`, inteiros dentro do período
    e com todos os pedidos já consultados."""
    congelado = {m: r for m, r in congelado.items() if f"{m}-01" >= inicio and m < fechado_ate}
    mes = inicio[:7]
    while mes in congelado:
        mes = _proximo_mes(mes)
    anteriores = [r for m in sorted(congelado) if m < mes for r in congelado[m]]
    desde = max(inicio, f"{mes}-01")
    if desde > fim:
        return anteriores, congelado
    novos, pendentes = _coletar(desde, fim, anteriores)
    novo = {m: congelado[m] for m in congelado if m < mes}
    por_mes: dict[str, list[dict]] = {}
    for r in novos:
        por_mes.setdefault(r["d"][:7], []).append(r)
    while mes < fechado_ate and f"{mes}-01" <= fim:
        if f"{mes}-01" >= inicio and mes not in pendentes:
            novo[mes] = por_mes.get(mes, [])
        mes = _proximo_mes(mes)
    return anteriores + novos, novo


def estoque_atual() -> list[dict]:
    """Produtos com saldo positivo hoje (todos os locais da filial), a custo médio."""
    hoje = time.strftime("%Y-%m-%d")
    itens = _paginar(
        "ListarPosEstoque",
        EP_ESTOQUE,
        lambda p: {"nPagina": p, "nRegPorPagina": 100, "dDataPosicao": _br(hoje), "cExibeTodos": "N"},
        "produtos",
        "nTotPaginas",
        paralelo=1,  # ListarPosEstoque recusa chamadas simultâneas
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
    if _empresa == "filial":
        _post(
            "CuponsFiscais",
            EP_CUPOM,
            {"nPagina": 1, "nRegPorPagina": 1, "dDtEmissaoDe": _br(hoje), "dDtEmissaoAte": _br(hoje)},
        )
        return "Conexão Omie OK (NF-e + NFC-e PDV, somente leitura)."
    return "Conexão Omie OK (NF-e, somente leitura)."
