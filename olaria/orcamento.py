# -*- coding: utf-8 -*-
"""Gera grade orçada mensal a partir do cadastro de despesas fixas."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DespesaCadastro:
    numero: int | None
    nome: str
    categoria: str
    valor: float | None
    periodicidade: str | None
    mes_pagamento: int | None
    intervalo_meses: int | None
    equivalente_mensal: float | None
    observacao: str | None


def _float(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _int(v) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def meses_com_pagamento(d: DespesaCadastro) -> set[int]:
    per = (d.periodicidade or "Mensal").strip().lower()
    mes_ini = d.mes_pagamento or 1
    intervalo = d.intervalo_meses or 1

    if per == "mensal":
        return set(range(1, 13))
    if per == "anual":
        m = max(1, min(12, mes_ini))
        return {m}
    if per == "semestral":
        iv = intervalo if intervalo > 0 else 6
        m1 = max(1, min(12, mes_ini))
        m2 = ((m1 - 1 + iv) % 12) + 1
        return {m1, m2}
    if per == "trimestral":
        iv = intervalo if intervalo > 0 else 3
        out = set()
        m = mes_ini
        for _ in range(4):
            out.add(max(1, min(12, m)))
            m = ((m - 1 + iv) % 12) + 1
        return out
    return set(range(1, 13))


def valor_orcado_mes(d: DespesaCadastro, mes: int) -> float:
    """Valor previsto no mês (1-12). Despesas sem valor fixo retornam 0."""
    if d.valor is None or d.valor <= 0:
        return 0.0
    if mes not in meses_com_pagamento(d):
        return 0.0
    per = (d.periodicidade or "Mensal").strip().lower()
    if per == "mensal":
        return d.valor
    return d.valor


def grade_orcada(cadastro: list[DespesaCadastro]) -> dict[str, list[float]]:
    """Nome da despesa -> 12 valores (Jan..Dez)."""
    grade: dict[str, list[float]] = {}
    for d in cadastro:
        if not d.nome:
            continue
        grade[d.nome] = [valor_orcado_mes(d, m) for m in range(1, 13)]
    return grade


def totais_mes(grade: dict[str, list[float]]) -> list[float]:
    tot = [0.0] * 12
    for vals in grade.values():
        for i, v in enumerate(vals):
            tot[i] += v
    return tot
