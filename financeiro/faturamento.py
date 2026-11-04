"""Faturamento líquido (NF-e + NFC-e PDV − devoluções), mesma regra do painel-omie de vendas."""
from __future__ import annotations

import html
import re
from collections import defaultdict

from . import omie

# Operações que não entram no faturamento (remessa etc.)
OP_EXCLUIDAS = frozenset({"14", "16", "24", "04"})

CFOP_SAIDA_NAO_VENDA = frozenset({
    "5151", "5152", "5155", "5156", "6151", "6152", "6155", "6156",
    "5201", "5202", "5208", "5209", "5210", "5410", "5411", "5409",
    "6201", "6202", "6208", "6209", "6210", "6410", "6411", "6409",
    "5910", "5911", "5949", "6910", "6911", "6949",
})
CFOP_DEVOLUCAO_VENDA = frozenset({"1201", "1202", "1410", "1411", "2201", "2202", "2410", "2411"})


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


def _iso_br(d: str) -> str:
    d = (d or "").strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", d):
        return d
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})$", d)
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else d[:10]


def _cfop(pr: dict) -> str:
    return re.sub(r"\D", "", str(pr.get("CFOP") or ""))


def _valor_item(pr: dict) -> float:
    return (
        _f(pr.get("vProd")) - _f(pr.get("vDesc"))
        + _f(pr.get("vFrete")) + _f(pr.get("vSeg")) + _f(pr.get("vOutro"))
    )


def _cancelada_nf(nf: dict) -> bool:
    ide = nf.get("ide") or {}
    if (ide.get("dCan") or "").strip() or (ide.get("dInut") or "").strip():
        return True
    return _sim(ide.get("cDeneg"))


def _codigo_operacao(nf: dict) -> str:
    ped, compl = nf.get("pedido") or {}, nf.get("compl") or {}
    for chave in ("codigo_operacao", "cCodOperacao", "opPedido", "cOpPedido"):
        v = ped.get(chave) or compl.get(chave)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def _nf_de_venda(nf: dict) -> bool:
    return not (_cancelada_nf(nf) or _codigo_operacao(nf) in OP_EXCLUIDAS
                or _sim((nf.get("pedido") or {}).get("cCancelado")))


def _por_dia(linhas: list[tuple[str, float]]) -> list[dict]:
    acc: dict[str, float] = defaultdict(float)
    for d, v in linhas:
        if d:
            acc[d] += v
    return [{"d": d, "v": round(acc[d], 2)} for d in sorted(acc)]


def _itens_nf_venda(nf: dict) -> list[tuple[str, float]]:
    ide = nf.get("ide") or {}
    data = _iso_br(str(ide.get("dEmi") or ""))
    if not data:
        return []
    out: list[tuple[str, float]] = []
    for det in nf.get("det") or []:
        pr = det.get("prod") or {}
        if not _texto(pr.get("xProd") or pr.get("cProd") or "") or _cfop(pr) in CFOP_SAIDA_NAO_VENDA:
            continue
        valor = _valor_item(pr)
        if valor > 0:
            out.append((data, valor))
    return out


def _itens_devolucao(nf: dict) -> list[tuple[str, float]]:
    if _cancelada_nf(nf):
        return []
    ide = nf.get("ide") or {}
    data = _iso_br(str(ide.get("dEmi") or ""))
    if not data:
        return []
    out: list[tuple[str, float]] = []
    for det in nf.get("det") or []:
        pr = det.get("prod") or {}
        if _cfop(pr) not in CFOP_DEVOLUCAO_VENDA:
            continue
        produto = _texto(pr.get("xProd") or pr.get("cProd") or "")
        valor = _valor_item(pr)
        if produto and valor > 0:
            out.append((data, -valor))
    return out


def _itens_cupom(cupom: dict) -> list[tuple[str, float]]:
    cab = cupom.get("cabecalhoCupom") or {}
    data = _iso_br(str(cab.get("dDtEmissaoCupom") or ""))
    if not data:
        return []
    out: list[tuple[str, float]] = []
    for item in cupom.get("itensCupom") or []:
        if _sim(item.get("cCupomCancelado")) or _sim(item.get("cItemCancelado")):
            continue
        if not _texto(item.get("xProd") or item.get("cCodigo") or ""):
            continue
        valor = _f(item.get("vItem"))
        if valor <= 0:
            valor = _f(item.get("vUnit")) * _f(item.get("nQuant")) - _f(item.get("vDesc")) + _f(item.get("vAcresc"))
        if valor > 0:
            out.append((data, valor))
    return out


def linhas(inicio: str, fim: str) -> list[dict]:
    """Valores por dia de emissão (vendas positivas, devoluções negativas)."""
    brutos: list[tuple[str, float]] = []
    for nf in omie.notas_fiscais(inicio, fim, "1"):
        if _nf_de_venda(nf):
            brutos.extend(_itens_nf_venda(nf))
    for cupom in omie.cupons_fiscais(inicio, fim):
        brutos.extend(_itens_cupom(cupom))
    for nf in omie.notas_fiscais(inicio, fim, "0"):
        brutos.extend(_itens_devolucao(nf))
    return _por_dia(brutos)


def resumo(linhas_dia: list[dict], inicio: str, fim: str) -> dict:
    por_mes: dict[str, float] = defaultdict(float)
    total = 0.0
    for r in linhas_dia:
        if inicio <= r["d"] <= fim:
            total += r["v"]
            por_mes[r["d"][:7]] += r["v"]
    return {"t": round(total, 2), "m": {k: round(v, 2) for k, v in sorted(por_mes.items())}}
