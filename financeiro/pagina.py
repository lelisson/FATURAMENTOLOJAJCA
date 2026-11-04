"""HTML do painel financeiro com dados e Chart.js embutidos (usado pelo Streamlit; só biblioteca padrão)."""
from __future__ import annotations

import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PAGINA = RAIZ / "financeiro" / "frontend" / "index.html"
CHART_JS = RAIZ / "frontend" / "vendor" / "chart.umd.min.js"


def montar_html(payload: dict, app: bool = False) -> str:
    """app=True: exibido dentro do Streamlit (sem o rótulo "Relatório"); False: arquivo para baixar."""
    dados = {**payload, "app": app}
    dados_js = json.dumps(dados, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    pagina = PAGINA.read_text(encoding="utf-8")
    chart_js = CHART_JS.read_text(encoding="utf-8")
    return pagina.replace('<script src="/vendor/chart.umd.min.js"></script>',
                          f"<script>{chart_js}</script>\n<script>window.__STATIC__={dados_js};</script>", 1)
