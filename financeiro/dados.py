"""Transforma o Movimento Financeiro da Omie em tabelas para o painel.

- Realizado (caixa): lançamentos em conta corrente (grupos CONTA_CORRENTE_*) pela data de pagamento.
  Cada título pago aparece também como CONTA_A_*; usar só a conta corrente evita contar duas vezes
  e inclui lançamentos diretos do extrato (tarifas, despesas sem título).
- Títulos: contas a pagar/receber (grupos CONTA_A_*) pela data de vencimento.
"""
from __future__ import annotations

import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import pandas as pd
from cryptography.fernet import Fernet, InvalidToken

from . import ambiente, faturamento, omie

# Mês corrente muda o tempo todo; o anterior ainda recebe baixas atrasadas; os mais antigos quase não mudam.
TTL_MES_ATUAL = 30 * 60
TTL_MES_ANTERIOR = 12 * 3600
TTL_MES_ANTIGO = 7 * 24 * 3600
TTL_CADASTROS = 12 * 3600
_cache: dict[tuple, tuple[float, object]] = {}
_trava = threading.Lock()

# Meses fechados também ficam em disco, cifrados (Fernet) com a chave da variável de usuário FIN_JCA_CACHE_KEY,
# para o painel não reconsultar o ano inteiro depois de reiniciar o PC. Sem a chave, o cache é só em memória.
ARQ_CACHE = Path(__file__).resolve().parents[1] / "data" / "cache_meses.enc"
_disco = {"lido": False, "sujo": False}

ORIGENS = {
    "BAXP": "Baixa de conta a pagar",
    "BAXR": "Baixa de conta a receber",
    "APBR": "Baixa automática (integração)",
    "EXTP": "Lançamento direto no extrato",
    "EXTR": "Lançamento direto no extrato",
    "TRAP": "Transferência entre contas",
    "TRAR": "Transferência entre contas",
    "DEVP": "Devolução",
    "DEVR": "Devolução",
    "VENR": "Venda",
    "APIR": "Venda (PDV / integração)",
    "RPTP": "Recebimento de mercadoria",
    "COMP": "Compra",
    "MANP": "Lançamento manual",
    "MANR": "Lançamento manual",
}
TRANSFERENCIAS = frozenset({"TRAP", "TRAR"})
SEM = "(não informado)"


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def meses(inicio: str, fim: str) -> list[tuple[str, str]]:
    """Fatias mensais [início, fim] dentro do período (para cache por mês)."""
    out = []
    d = date.fromisoformat(inicio[:8] + "01")
    f = date.fromisoformat(fim)
    while d <= f:
        prox = date(d.year + d.month // 12, d.month % 12 + 1, 1)
        ini_m = max(d, date.fromisoformat(inicio))
        fim_m = min(f, date.fromordinal(prox.toordinal() - 1))
        out.append((ini_m.isoformat(), fim_m.isoformat()))
        d = prox
    return out


def cadastros() -> dict[str, dict]:
    cats = omie.categorias()
    desc = {c["codigo"]: (c.get("descricao") or c.get("descricao_padrao") or c["codigo"]).strip() for c in cats}
    categorias = {}
    for c in cats:
        cod = c["codigo"]
        sup = c.get("categoria_superior") or ".".join(cod.split(".")[:2])
        categorias[cod] = {
            "categoria": desc[cod],
            "grupo": desc.get(sup, desc[cod]),
            "transferencia": c.get("transferencia") == "S",
        }
    contas = {int(c["nCodCC"]): (c.get("descricao") or str(c["nCodCC"])).strip()
              for c in omie.contas_correntes()}
    deps = {str(d["codigo"]): (d.get("descricao") or str(d["codigo"])).strip() for d in omie.departamentos()}
    pessoas = {int(p["codigo_cliente"]): ((p.get("nome_fantasia") or p.get("razao_social") or "").strip(),
                                          _digitos(p.get("cnpj_cpf")))
               for p in omie.clientes_fornecedores()}
    raizes = {_digitos(e.get("cnpj"))[:8] for e in omie.empresas()} - {""}
    return {"categorias": categorias, "contas": contas, "departamentos": deps, "pessoas": pessoas,
            "raizes_jca": raizes}


def _digitos(s) -> str:
    return re.sub(r"\D", "", str(s or ""))


_GOVERNO = re.compile(r"\b(SEFAZ|FGTS|INSS|RECEITA FEDERAL|PREFEITURA|MUNICIPIO|DARF|SIMPLES NACIONAL|SECRETARIA|"
                      r"TLF|DETRAN|MINISTERIO|TRIBUNAL|CONSELHO REGIONAL)\b", re.I)
_BANCO = re.compile(r"\b(BANCO|BANESE|BRADESCO|ITAU|ITAÚ|SANTANDER|SICOOB|SICREDI|NUBANK|CAIXA ECONOMICA|"
                    r"STONE|CIELO|PAGSEGURO|MERCADO PAGO|GETNET|SAFRAPAY|REDE S\.?A)\b", re.I)


def _classe(nome: str, doc: str, grupo: str, saida: bool, raizes: set[str]) -> str:
    # Mesma raiz de CNPJ = outro estabelecimento da própria JCA (matriz/filiais): não é custo nem receita.
    if len(doc) == 14 and doc[:8] in raizes:
        return "Entre filiais"
    if not saida:
        return "Clientes"
    if grupo == "Despesas com Pessoal" or len(doc) == 11:
        return "Pessoal"
    if grupo.startswith("Impostos") or _GOVERNO.search(nome):
        return "Impostos e governo"
    if "Financeira" in grupo or _BANCO.search(nome):
        return "Bancos e financeiras"
    if nome == SEM:
        return "Sem favorecido"
    return "Fornecedores"


def _comuns(d: dict, cad: dict) -> dict:
    cat = cad["categorias"].get(d.get("cCodCateg") or "", {})
    nome, doc_cad = cad["pessoas"].get(int(d.get("nCodCliente") or 0), ("", ""))
    nome = nome or SEM
    doc = _digitos(d.get("cCPFCNPJCliente")) or doc_cad
    grupo = cat.get("grupo", SEM)
    classe = _classe(nome, doc, grupo, d.get("cNatureza") == "P", cad["raizes_jca"])
    return {
        "categoria_cod": d.get("cCodCateg") or "",
        "categoria": cat.get("categoria", d.get("cCodCateg") or SEM),
        "grupo": grupo,
        "conta": cad["contas"].get(int(d.get("nCodCC") or 0), SEM),
        "pessoa": nome,
        "classe": classe,
        "documento": (d.get("cNumDocFiscal") or "").strip(),
        "tipo_doc": d.get("cTipo") or "",
        "origem": ORIGENS.get(d.get("cOrigem") or "", d.get("cOrigem") or ""),
        "transferencia": (d.get("cOrigem") in TRANSFERENCIAS or cat.get("transferencia", False)
                          or classe == "Entre filiais"),
        "titulo": int(d.get("nCodTitulo") or 0),
    }


def realizado_bruto(inicio: str, fim: str) -> list[dict]:
    return omie.movimentos_pagos(inicio, fim)


def realizado(brutos: list[dict], cad: dict, deps_titulo: dict[int, list[tuple[str, float]]]) -> pd.DataFrame:
    linhas = []
    vistos = set()
    for m in brutos:
        d = m.get("detalhes") or {}
        if not str(d.get("cGrupo", "")).startswith("CONTA_CORRENTE") or d.get("cStatus") == "CANCELADO":
            continue
        chave = d.get("nCodMovCC") or (d.get("nCodTitulo"), d.get("nCodBaixa"), d.get("dDtPagamento"))
        if chave in vistos:
            continue
        vistos.add(chave)
        valor = abs(_f(d.get("nValorMovCC")))
        if not valor:
            continue
        saida = d.get("cNatureza") == "P"
        linhas.append({
            "data": omie.iso(d.get("dDtPagamento") or d.get("dDtCredito") or ""),
            "tipo": "Saída" if saida else "Entrada",
            "valor": valor,
            "valor_sinal": -valor if saida else valor,
            **_comuns(d, cad),
        })
    df = pd.DataFrame(linhas)
    if df.empty:
        return df
    df["data"] = pd.to_datetime(df["data"], errors="coerce")
    df["mes"] = df["data"].dt.to_period("M").astype(str)
    df["departamento"] = df["titulo"].map(lambda t: _dep_principal(deps_titulo.get(t), cad))
    return df


def _dep_principal(deps: list[tuple[str, float]] | None, cad: dict) -> str:
    if not deps:
        return SEM
    cod = max(deps, key=lambda x: x[1])[0]
    return cad["departamentos"].get(cod, cod)


def titulos_bruto(inicio: str, fim: str) -> list[dict]:
    return omie.movimentos(inicio, fim)


def em_aberto_bruto() -> list[dict]:
    return omie.paginar(
        "ListarMovimentos",
        lambda p: {"nPagina": p, "nRegPorPagina": 500, "cStatus": "EMABERTO", "cExibirDepartamentos": "S"},
        "movimentos",
        "nTotPaginas",
    )


def titulos(brutos: list[dict], cad: dict) -> pd.DataFrame:
    linhas = []
    vistos = set()
    for m in brutos:
        d = m.get("detalhes") or {}
        grupo = d.get("cGrupo")
        if grupo not in ("CONTA_A_PAGAR", "CONTA_A_RECEBER") or d.get("cStatus") == "CANCELADO":
            continue
        if d.get("nCodTitulo") in vistos:
            continue
        vistos.add(d.get("nCodTitulo"))
        r = m.get("resumo") or {}
        deps = [(str(x.get("cCodDepartamento")), _f(x.get("nDistrPercentual"))) for x in m.get("departamentos") or []]
        linhas.append({
            "natureza": "A pagar" if grupo == "CONTA_A_PAGAR" else "A receber",
            "status": d.get("cStatus") or "",
            "vencimento": omie.iso(d.get("dDtVenc") or ""),
            "emissao": omie.iso(d.get("dDtEmissao") or ""),
            "pagamento": omie.iso(d.get("dDtPagamento") or ""),
            "parcela": d.get("cNumParcela") or "",
            "valor": _f(d.get("nValorTitulo")),
            "pago": _f(r.get("nValPago")),
            "aberto": _f(r.get("nValAberto")),
            "juros_multa": _f(r.get("nJuros")) + _f(r.get("nMulta")),
            "desconto": _f(r.get("nDesconto")),
            "departamento": _dep_principal(deps, cad),
            "_deps": deps,
            **_comuns(d, cad),
        })
    df = pd.DataFrame(linhas)
    if df.empty:
        return df
    for c in ("vencimento", "emissao", "pagamento"):
        df[c] = pd.to_datetime(df[c], errors="coerce")
    df["mes"] = df["vencimento"].dt.to_period("M").astype(str)
    return df


def deps_por_titulo(brutos: list[dict]) -> dict[int, list[tuple[str, float]]]:
    out = {}
    for m in brutos:
        d = m.get("detalhes") or {}
        if m.get("departamentos") and d.get("nCodTitulo"):
            out[int(d["nCodTitulo"])] = [(str(x.get("cCodDepartamento")), _f(x.get("nDistrPercentual")))
                                         for x in m["departamentos"]]
    return out


def _em_cache(chave: tuple, ttl: float, buscar, forcar: bool, antigos: list | None = None):
    with _trava:
        item = _cache.get(chave)
    if item and not forcar and time.time() - item[0] < ttl:
        return item[1]
    try:
        valor = buscar()
    except omie.OmieBloqueada:
        if item is None or antigos is None:
            raise
        antigos.append(chave)
        return item[1]
    with _trava:
        _cache[chave] = (time.time(), valor)
    return valor


def _fernet() -> Fernet | None:
    chave = ambiente.ler("FIN_JCA_CACHE_KEY")
    return Fernet(chave.encode()) if chave else None


def _mes_fechado(chave: tuple, mes_atual: str) -> bool:
    return chave[0] in ("pagos", "venc", "fat") and chave[2][:7] < mes_atual


def _ler_disco() -> None:
    if _disco["lido"]:
        return
    _disco["lido"] = True
    f = _fernet()
    if not f or not ARQ_CACHE.exists():
        return
    try:
        itens = json.loads(f.decrypt(ARQ_CACHE.read_bytes()))
    except (InvalidToken, ValueError, OSError):
        return
    with _trava:
        for k, (ts, valor) in itens.items():
            _cache.setdefault(tuple(k.split("|")), (ts, valor))


def _gravar_disco(mes_atual: str) -> None:
    f = _fernet()
    if not f or not _disco["sujo"]:
        return
    with _trava:
        itens = {"|".join(k): v for k, v in _cache.items() if _mes_fechado(k, mes_atual)}
    ARQ_CACHE.parent.mkdir(parents=True, exist_ok=True)
    tmp = ARQ_CACHE.with_suffix(".tmp")
    tmp.write_bytes(f.encrypt(json.dumps(itens, separators=(",", ":")).encode()))
    tmp.replace(ARQ_CACHE)
    _disco["sujo"] = False


def carregar(inicio: str, fim: str, forcar: bool = False) -> dict:
    """Busca o período em fatias mensais.

    ListarMovimentos vai em fila: a Omie recusa uma segunda chamada simultânea do método e,
    se insistir, passa a exigir espera. Os cadastros (outros métodos) correm em paralelo à fila."""
    _ler_disco()
    mes_atual = date.today().isoformat()[:7]
    mes_anterior = (pd.Period(mes_atual) - 1).strftime("%Y-%m")

    def ttl(fim_m: str) -> float:
        m = fim_m[:7]
        return TTL_MES_ATUAL if m >= mes_atual else TTL_MES_ANTERIOR if m == mes_anterior else TTL_MES_ANTIGO

    fila = {("aberto",): (TTL_MES_ATUAL, em_aberto_bruto)}
    for ini_m, fim_m in meses(inicio, fim):
        fila[("pagos", ini_m, fim_m)] = (ttl(fim_m), lambda a=ini_m, b=fim_m: realizado_bruto(a, b))
        fila[("venc", ini_m, fim_m)] = (ttl(fim_m), lambda a=ini_m, b=fim_m: titulos_bruto(a, b))
        fila[("fat", ini_m, fim_m)] = (ttl(fim_m), lambda a=ini_m, b=fim_m: faturamento.linhas(a, b))

    with _trava:
        antes = {k: _cache[k][0] for k in fila if k in _cache}
    antigos: list[tuple] = []
    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            f_cad = ex.submit(_em_cache, ("cadastros",), TTL_CADASTROS, cadastros, forcar, antigos)
            res = {k: _em_cache(k, t, f, forcar and t == TTL_MES_ATUAL, antigos) for k, (t, f) in fila.items()}
            cad = f_cad.result()
    finally:
        with _trava:
            if any(k in _cache and _mes_fechado(k, mes_atual) and _cache[k][0] != antes.get(k) for k in fila):
                _disco["sujo"] = True
        _gravar_disco(mes_atual)

    aberto = res.pop(("aberto",))
    fat_dia = [r for k, v in res.items() if k[0] == "fat" for r in v]
    pagos = [m for k, v in res.items() if k[0] == "pagos" for m in v]
    venc = [m for k, v in res.items() if k[0] == "venc" for m in v]
    deps = deps_por_titulo([*venc, *aberto, *pagos])
    with _trava:
        atualizado = _cache[("aberto",)][0]
    return {
        "realizado": realizado(pagos, cad, deps),
        "titulos": titulos(venc, cad),
        "aberto": titulos(aberto, cad),
        "faturamento_dia": fat_dia,
        "atualizado_em": atualizado,
        "desatualizado": bool(antigos),
    }
