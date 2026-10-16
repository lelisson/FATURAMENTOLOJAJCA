"""Monta o painel (frontend/index.html) como HTML único, com dados e Chart.js embutidos.

Usado pelo relatório estático (FastAPI) e pelo app Streamlit; não depende de servidor nem de internet.
"""
import json
from pathlib import Path

from . import relatorio

ROOT = Path(__file__).resolve().parents[2]
FRONT = ROOT / "frontend"
TAG_CHART = '<script src="/vendor/chart.umd.min.js"></script>'


def montar_html(rows, rows_prev, inicio, fim, p_ini, p_fim, empresa, atualizado, fonte, estoque=None,
                modo: str = "relatorio", tem_pdv: bool | None = None, hist=None, hist_inicio=None,
                hist_fim=None) -> str:
    titulo_prev = relatorio.nome_periodo(p_ini, p_fim)
    if tem_pdv is None:
        tem_pdv = "matriz" not in (empresa or "").lower()
    dados = {
        "rows": rows, "prev": rows_prev, "inicio": inicio, "fim": fim,
        "prev_inicio": p_ini, "prev_fim": p_fim, "fonte": fonte, "empresa": empresa,
        "titulo": relatorio.nome_periodo(inicio, fim),
        "prev_label": titulo_prev[0].lower() + titulo_prev[1:] if titulo_prev[0].isalpha() else titulo_prev,
        "atualizado_em": atualizado, "estoque": estoque, "modo": modo, "tem_pdv": bool(tem_pdv),
    }
    # Histórico além do período (seção Relatório: comparativos e previsão).
    if hist is not None:
        dados.update(hist=hist, hist_inicio=hist_inicio, hist_fim=hist_fim)
    html = (FRONT / "index.html").read_text(encoding="utf-8")
    if TAG_CHART not in html:
        raise RuntimeError("frontend/index.html sem a tag do Chart.js local.")
    chart_js = (FRONT / "vendor/chart.umd.min.js").read_text(encoding="utf-8")
    payload = json.dumps(dados, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = html.replace(TAG_CHART, f"<script>{chart_js}</script>", 1)
    return html.replace("</head>", f"<script>window.__STATIC__={payload};</script>\n</head>", 1)
