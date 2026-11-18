# -*- coding: utf-8 -*-
"""
Sincroniza receitas (contas recebidas) do Omie → aba Faturamento da planilha.

Despesas (Lançamentos) continuam no Excel até existir mapeamento Omie → linhas do cadastro.
Sempre gera backup .bak antes de gravar.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .omie_client import EP_CONTAS_RECEBER, omie_call
from .planilha_io import atualizar_faturamento_meses, caminho_planilha, carregar_faturamento

from .config import OMIE_LINHA_FATURAMENTO


def _f(v) -> float:
    if v is None or v == "":
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _parse_data_br(s: str | None) -> datetime | None:
    if not s:
        return None
    s = str(s).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:10], fmt)
        except ValueError:
            continue
    return None


def _mes_idx(dt: datetime | None) -> int | None:
    if not dt:
        return None
    return dt.month - 1


def _valor_recebido(item: dict) -> float:
    for k in ("nValorRecebido", "valor_recebido", "nValorTitulo", "valor_documento"):
        if k in item and item[k] not in (None, ""):
            return _f(item[k])
    cab = item.get("cabecalho") or item.get("Cabecalho") or {}
    if isinstance(cab, dict):
        for k in ("nValorTitulo", "nValorRecebido", "valor_documento"):
            if k in cab:
                return _f(cab[k])
    return 0.0


def _data_recebimento(item: dict) -> datetime | None:
    for k in ("dDtRecebimento", "data_recebimento", "dDtCredito", "data_credito", "dDtPagamento"):
        dt = _parse_data_br(item.get(k))
        if dt:
            return dt
    cab = item.get("cabecalho") or item.get("Cabecalho") or {}
    if isinstance(cab, dict):
        for k in ("dDtRecebimento", "dDtCredito", "dDtVenc"):
            dt = _parse_data_br(cab.get(k))
            if dt:
                return dt
    return None


def _status_recebido(item: dict) -> bool:
    st = (
        item.get("cStatus")
        or item.get("status_titulo")
        or item.get("status")
        or ""
    )
    s = str(st).upper()
    if any(x in s for x in ("RECEB", "LIQUID", "BAIXAD")):
        return True
    if item.get("bRecebido") in (True, "S", "s", 1):
        return True
    return False


def listar_recebimentos_por_mes(ano: int) -> list[float]:
    """Soma recebimentos por mês (0=Jan) no ano informado."""
    totais = [0.0] * 12
    pagina = 1
    de = f"01/01/{ano}"
    ate = f"31/12/{ano}"
    while True:
        param = {
            "nPagina": pagina,
            "nRegPorPagina": 500,
            "filtrar_por_data_de": de,
            "filtrar_por_data_ate": ate,
        }
        resp = omie_call("ListarContasReceber", EP_CONTAS_RECEBER, param)
        registros = (
            resp.get("conta_receber_cadastro")
            or resp.get("conta_receber_lista")
            or resp.get("cadastro")
            or []
        )
        if not registros:
            break
        for item in registros:
            if not _status_recebido(item):
                continue
            dt = _data_recebimento(item)
            if not dt or dt.year != ano:
                continue
            mi = _mes_idx(dt)
            if mi is None:
                continue
            totais[mi] += _valor_recebido(item)
        total_pag = int(resp.get("nTotPaginas") or resp.get("total_de_paginas") or 1)
        if pagina >= total_pag:
            break
        pagina += 1
    return totais


def sincronizar_faturamento_omie(path: Path | None, ano: int) -> str:
    p = caminho_planilha(path)
    linhas, _ = carregar_faturamento(p)
    linha = OMIE_LINHA_FATURAMENTO
    if linha not in linhas:
        linha = linhas[0] if linhas else OMIE_LINHA_FATURAMENTO

    receitas = listar_recebimentos_por_mes(ano)
    alterados = sum(1 for v in receitas if v > 0)
    if alterados == 0:
        return f"Omie: nenhuma receita recebida em {ano} para gravar em Faturamento."
    atualizar_faturamento_meses(linha, receitas, p)
    return f"Omie: Faturamento atualizado ({alterados} mês(es) com valor) · linha «{linha}»."


def sincronizar_omie(path: Path | None, ano: int) -> str:
    from .omie_client import testar_conexao

    testar_conexao()
    return sincronizar_faturamento_omie(path, ano)
