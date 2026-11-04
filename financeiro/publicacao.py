"""Monta os dados do painel financeiro para publicação (mesmo formato do /api/dados do painel local)."""
from __future__ import annotations

import time
from datetime import date

import pandas as pd

from . import dados, faturamento


def _iso(s: pd.Series) -> list[str]:
    return s.dt.strftime("%Y-%m-%d").fillna("").tolist()


def _lancamentos(df: pd.DataFrame) -> list[dict]:
    if df.empty:
        return []
    out = pd.DataFrame({
        "d": _iso(df["data"]), "t": df["tipo"].map({"Entrada": "E", "Saída": "S"}), "v": df["valor"].round(2),
        "g": df["grupo"], "c": df["categoria"], "p": df["pessoa"], "k": df["classe"], "cc": df["conta"],
        "dp": df["departamento"], "doc": df["documento"], "o": df["origem"], "tr": df["transferencia"].astype(int),
    })
    return out.to_dict("records")


def _titulos(df: pd.DataFrame) -> list[dict]:
    if df.empty:
        return []
    out = pd.DataFrame({
        "n": df["natureza"].map({"A pagar": "P", "A receber": "R"}), "s": df["status"],
        "dv": _iso(df["vencimento"]), "dg": _iso(df["pagamento"]), "v": df["valor"].round(2),
        "pg": df["pago"].round(2), "ab": df["aberto"].round(2), "g": df["grupo"], "c": df["categoria"],
        "p": df["pessoa"], "k": df["classe"], "cc": df["conta"], "dp": df["departamento"], "doc": df["documento"],
        "par": df["parcela"], "tr": df["transferencia"].astype(int),
    })
    return out.to_dict("records")


def montar(inicio: str, fim: str | None = None) -> dict:
    """Consulta a Omie (somente leitura) em meses inteiros e recorta o período. Erros da Omie sobem."""
    hoje = date.today().isoformat()
    fim = min(fim or hoje, hoje)
    ini_m = inicio[:8] + "01"
    fim_m = min(f"{fim[:7]}-{pd.Period(fim[:7]).days_in_month:02d}", hoje)
    base = dados.carregar(ini_m, fim_m)
    real, tit = base["realizado"], base["titulos"]
    if not real.empty:
        real = real[(real["data"] >= inicio) & (real["data"] <= fim)]
    if not tit.empty:
        tit = tit[(tit["vencimento"] >= inicio) & (tit["vencimento"] <= fim)]
    return {
        "inicio": inicio, "fim": fim, "hoje": hoje,
        "atualizado_em": base["atualizado_em"], "desatualizado": base["desatualizado"],
        "lanc": _lancamentos(real),
        "titulos": _titulos(tit),
        "aberto": _titulos(base["aberto"]),
        "fat": faturamento.resumo(base["faturamento_dia"], inicio, fim),
        "estatico": True,
        "gerado_em": time.time(),
    }
