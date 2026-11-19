"""HTML do painel da Olaria no mesmo visual da Matriz/Filial (Chart.js embutido)."""
from __future__ import annotations

import json
import time
from pathlib import Path

from .config import TETO_GASTOS_MENSAL
from .planilha_io import snapshot_dados

RAIZ = Path(__file__).resolve().parents[1]
PAGINA = Path(__file__).resolve().parent / "frontend" / "index.html"
CHART_JS = RAIZ / "frontend" / "vendor" / "chart.umd.min.js"


def payload(app: bool = False) -> dict:
    d = snapshot_dados()
    return {
        "app": app,
        "gerado_em": time.time(),
        "ano": d["ano"],
        "meses": d["meses"],
        "teto": TETO_GASTOS_MENSAL,
        "despesa_mes": [round(x, 2) for x in d["despesa_mes"]],
        "receita_mes": [round(x, 2) for x in d["receita_mes"]],
        "despesa_ano": round(d["despesa_ano"], 2),
        "receita_ano": round(d["receita_ano"], 2),
        "media_despesa_mes": round(d["media_despesa_mes"], 2),
        "despesas": d["despesas"],
        "categorias": d["categorias"],
        "realizado": [[round(v, 2) for v in linha] for linha in d["realizado"]],
        "por_categoria_ano": {k: round(v, 2) for k, v in d["por_categoria_ano"].items()},
    }


def montar_html(dados: dict | None = None, app: bool = False) -> str:
    dados = {**(dados or payload(app=app)), "app": app}
    dados_js = json.dumps(dados, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    pagina = PAGINA.read_text(encoding="utf-8")
    chart_js = CHART_JS.read_text(encoding="utf-8")
    return pagina.replace(
        '<script src="/vendor/chart.umd.min.js"></script>',
        f"<script>{chart_js}</script>\n<script>window.__STATIC__={dados_js};</script>",
        1,
    )
