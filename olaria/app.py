# -*- coding: utf-8 -*-
"""Dashboard interativo somente leitura — dados no Excel (Lançamentos / Faturamento)."""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from .config import (
    CATEGORIAS_PADRAO,
    GALPAO_NOME,
    MESES,
    PLANILHA_PADRAO,
    TETO_GASTOS_MENSAL,
    TITULO_PAINEL,
)
from .atualizacao import forcar_atualizacao
from .omie_client import credenciais_configuradas
from .planilha_io import carregar_cadastro, mtime_planilha, snapshot_dados
from .seguranca import acesso_autorizado

try:
    from streamlit_autorefresh import st_autorefresh
except ImportError:
    st_autorefresh = None

C_BG = "#0B1220"
C_CARD = "#151D2E"
C_BORDER = "#2A3548"
C_TEXT = "#E8EDF4"
C_MUTED = "#8B9BB4"
C_ACCENT = "#00B4FF"
C_OK = "#00E676"
C_ALERT = "#FF5252"
C_REAL = "#00B4FF"
C_REC = "#26A69A"


def br_moeda(v: float) -> str:
    if v != v:
        return "R$ 0,00"
    neg = v < 0
    s = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"-R$ {s}" if neg else f"R$ {s}"


def br_num(v: float, casas: int = 1) -> str:
    s = f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s


def indices_periodo(modo: str, mes_ini: int, mes_fim: int, mes_unico: int) -> list[int]:
    if modo == "Ano inteiro":
        return list(range(12))
    if modo == "Um mês":
        return [mes_unico]
    a, b = min(mes_ini, mes_fim), max(mes_ini, mes_fim)
    return list(range(a, b + 1))


def rotulo_periodo(ano: int, idx: list[int]) -> str:
    if len(idx) == 12:
        return f"Ano {ano}"
    if len(idx) == 1:
        return f"{MESES[idx[0]]}/{ano}"
    return f"{MESES[idx[0]]}–{MESES[idx[-1]]}/{ano}"


def totais_por_categoria_periodo(d: dict, idx: list[int], categorias_filtro: list[str] | None) -> dict[str, float]:
    por: dict[str, float] = {}
    for cat, linha in zip(d["categorias"], d["realizado"]):
        if categorias_filtro and cat not in categorias_filtro:
            continue
        por[cat] = por.get(cat, 0.0) + sum(linha[i] for i in idx)
    return por


def despesas_por_departamento_periodo(
    d: dict, idx: list[int], categorias_filtro: list[str] | None
) -> list[dict]:
    linhas: list[dict] = []
    for nome, cat, real in zip(d["despesas"], d["categorias"], d["realizado"]):
        if categorias_filtro and cat not in categorias_filtro:
            continue
        total = sum(real[i] for i in idx)
        if total == 0:
            continue
        linhas.append({"Departamento": cat, "Despesa": nome, "Total": total})
    return linhas


def tabela_departamentos(cat_df: pd.DataFrame, total_periodo: float) -> pd.DataFrame:
    out = cat_df.copy()
    out.columns = ["Departamento", "Total"]
    out = out.sort_values("Total", ascending=False)
    out["Total (R$)"] = out["Total"].apply(br_moeda)
    out["Participação"] = out["Total"].apply(
        lambda v: f"{br_num(100.0 * v / total_periodo if total_periodo else 0.0)} %"
    )
    return out[["Departamento", "Total (R$)", "Participação"]]


PALETA_DEPARTAMENTOS = [
    C_ACCENT,
    "#5C6BC0",
    C_REC,
    "#FFB300",
    "#AB47BC",
    "#EF5350",
    "#78909C",
    "#FFA726",
]


def cores_departamentos(n: int) -> list[str]:
    return PALETA_DEPARTAMENTOS[:n]


def html_lista_departamentos(cat_df: pd.DataFrame, total_periodo: float, cores: list[str]) -> str:
    itens: list[str] = []
    for i, row in enumerate(cat_df.itertuples(index=False)):
        pct = 100.0 * row.Realizado / total_periodo if total_periodo else 0.0
        cor = cores[i] if i < len(cores) else C_MUTED
        itens.append(
            f'<li class="dep-item">'
            f'<span class="dep-swatch" style="background:{cor};" aria-hidden="true"></span>'
            f'<span class="dep-name">{row.Categoria}</span>'
            f'<span class="dep-val">{br_moeda(row.Realizado)}</span>'
            f'<span class="dep-pct">{br_num(pct)} %</span>'
            f"</li>"
        )
    return (
        '<ul class="dep-list" role="list" aria-label="Totais por departamento">'
        + "".join(itens)
        + "</ul>"
    )


def inject_css() -> None:
    st.markdown(
        f"""
<style>
    .stApp {{ background: linear-gradient(165deg, {C_BG} 0%, #0F1A2E 45%, #0B1220 100%); }}
    [data-testid="stSidebar"] {{ background: #0A101C; border-right: 1px solid {C_BORDER}; }}
    [data-testid="stHorizontalBlock"]:has(.titulo-painel) {{
        background: linear-gradient(90deg, #0D2847 0%, #152238 100%);
        border: 1px solid {C_BORDER}; border-radius: 12px;
        padding: 0.95rem 1.15rem 0.95rem 1.35rem !important;
        margin-bottom: 1rem;
        box-shadow: 0 4px 24px rgba(0,0,0,0.35);
        align-items: center !important;
    }}
    .titulo-painel {{
        margin: 0; font-size: 1.45rem; font-weight: 700; color: {C_TEXT}; line-height: 1.25;
    }}
    [data-testid="stHorizontalBlock"]:has(.titulo-painel) .stButton > button {{
        min-height: 3.4rem;
        font-size: 1.12rem;
        font-weight: 700;
        padding: 0.7rem 1.4rem;
        border-radius: 10px;
        width: 100%;
    }}
    .painel-header p {{ margin: 0.35rem 0 0; color: {C_MUTED}; font-size: 0.82rem; }}
    .medidor {{
        background: {C_CARD}; border: 1px solid {C_BORDER}; border-radius: 12px;
        padding: 1rem 1.1rem; min-height: 118px;
        box-shadow: 0 2px 12px rgba(0,0,0,0.28), inset 0 1px 0 rgba(255,255,255,0.04);
        position: relative; margin: 0 0 0.75rem 0;
    }}
    .medidor::before {{
        content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 4px;
        background: var(--bar-color, {C_ACCENT});
    }}
    .medidor-label {{
        font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.12em;
        color: {C_MUTED}; font-weight: 600;
    }}
    .medidor-valor {{
        font-size: 1.65rem; font-weight: 800; font-variant-numeric: tabular-nums;
        margin: 0.35rem 0 0.15rem; line-height: 1.15;
    }}
    .medidor-sub {{ font-size: 0.78rem; color: {C_MUTED}; }}
    .card-section-title {{
        font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.1em;
        color: {C_MUTED}; font-weight: 700; margin-bottom: 0.5rem;
    }}
    .md-card-title {{
        font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.12em;
        color: {C_MUTED}; font-weight: 700; margin: 0 0 0.5rem 0;
    }}
    [data-testid="stVerticalBlockBorderWrapper"] {{
        background: {C_CARD} !important;
        border-color: {C_BORDER} !important;
        border-radius: 12px !important;
        box-shadow: 0 2px 12px rgba(0,0,0,0.28);
        padding: 0.85rem 1rem 0.65rem !important;
        margin-bottom: 0.75rem;
    }}
    .dep-figure {{ margin: 0; padding: 0; }}
    .dep-list {{
        list-style: none; margin: 0.65rem 0 0; padding: 0;
        border-top: 1px solid {C_BORDER};
    }}
    .dep-item {{
        display: grid;
        grid-template-columns: 12px 1fr auto auto;
        gap: 0.45rem 0.55rem;
        align-items: center;
        padding: 0.42rem 0;
        border-bottom: 1px solid rgba(42, 53, 72, 0.65);
        font-size: 0.82rem;
    }}
    .dep-item:last-child {{ border-bottom: none; }}
    .dep-swatch {{
        width: 10px; height: 10px; border-radius: 2px; display: block;
    }}
    .dep-name {{ color: {C_TEXT}; font-weight: 600; line-height: 1.25; }}
    .dep-val {{
        color: {C_MUTED}; font-variant-numeric: tabular-nums;
        font-size: 0.78rem; white-space: nowrap;
    }}
    .dep-pct {{
        color: {C_ACCENT}; font-weight: 700; font-variant-numeric: tabular-nums;
        font-size: 0.78rem; min-width: 3.1rem; text-align: right;
    }}
    .dep-card-chart [data-testid="stPlotlyChart"] {{
        min-height: 0 !important;
    }}
    .badge-leitura {{
        display: inline-block; margin-top: 0.5rem; padding: 0.2rem 0.55rem;
        border-radius: 6px; font-size: 0.72rem; font-weight: 600;
        background: rgba(0,180,255,0.12); color: {C_ACCENT}; letter-spacing: 0.04em;
    }}
    [data-testid="stVerticalBlockBorderWrapper"]:has(.filtro-card-root) {{
        margin-bottom: 1rem !important;
    }}
    .filtro-card-root ~ * .filtro-label,
    [data-testid="stVerticalBlockBorderWrapper"]:has(.filtro-card-root) .filtro-label {{
        font-size: 0.88rem; text-transform: uppercase; letter-spacing: 0.1em;
        color: {C_TEXT}; font-weight: 700; margin-bottom: 0.55rem;
    }}
    [data-testid="stVerticalBlockBorderWrapper"]:has(.filtro-card-root) .filtro-hint {{
        font-size: 0.82rem; color: {C_MUTED}; margin-bottom: 0.65rem;
    }}
    /* Linha Ano + Jan…Dez (pílulas de período) */
    div[data-testid="stPills"] {{
        flex-wrap: wrap;
        gap: 0.55rem !important;
    }}
    div[data-testid="stPills"] button,
    div[data-testid="stPills"] [role="radio"],
    div[data-testid="stPills"] [data-baseweb="button"],
    button[data-testid="stBaseButton-pills"],
    button[data-testid="stBaseButton-pillsActive"] {{
        min-width: 3.75rem !important;
        min-height: 3.15rem !important;
        font-weight: 700 !important;
        font-size: 1.2rem !important;
        line-height: 1.2 !important;
        padding: 0.55rem 1.05rem !important;
        border-radius: 9px !important;
    }}
    div[data-testid="stPills"] button p,
    div[data-testid="stPills"] button span,
    div[data-testid="stPills"] [data-baseweb="button"] p,
    div[data-testid="stPills"] [data-baseweb="button"] span {{
        font-size: 1.2rem !important;
        font-weight: 700 !important;
    }}
    .periodo-banner {{
        font-size: 1.65rem; font-weight: 800; color: {C_ACCENT};
        text-align: center; margin-top: 0.75rem; padding-top: 0.65rem;
        border-top: 1px solid {C_BORDER}; letter-spacing: 0.03em;
    }}
    .periodo-detalhe {{
        font-size: 1.35rem; font-weight: 700; color: {C_MUTED};
        margin-bottom: 0.75rem;
    }}
    .periodo-detalhe strong {{ color: {C_ACCENT}; font-size: 1.45rem; }}
</style>
        """,
        unsafe_allow_html=True,
    )


def html_medidor(label: str, valor: str, sub: str, bar: str) -> str:
    return f"""
<div class="medidor" style="--bar-color: {bar};">
  <div class="medidor-label">{label}</div>
  <div class="medidor-valor" style="color:{bar};">{valor}</div>
  <div class="medidor-sub">{sub}</div>
</div>
"""


def fig_gauge_valor(titulo: str, valor: float, maximo: float, cor: str) -> go.Figure:
    mx = max(maximo, valor * 1.08, 1.0)
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=valor,
            number={"prefix": "R$ ", "valueformat": ",.2f", "font": {"size": 26, "color": C_TEXT}},
            title={"text": titulo, "font": {"size": 13, "color": C_MUTED}},
            gauge={
                "axis": {"range": [0, mx], "tickcolor": C_BORDER},
                "bar": {"color": cor, "thickness": 0.75},
                "bgcolor": C_BG,
                "borderwidth": 0,
            },
        )
    )
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", height=260, margin=dict(l=24, r=24, t=48, b=8))
    return fig


def fig_gauge_pct(titulo: str, pct: float, cor: str) -> go.Figure:
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=pct,
            number={"suffix": " %", "font": {"size": 30, "color": cor}},
            title={"text": titulo, "font": {"size": 13, "color": C_MUTED}},
            gauge={"axis": {"range": [0, 100]}, "bar": {"color": cor}, "bgcolor": C_BG},
        )
    )
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", height=260, margin=dict(l=24, r=24, t=48, b=8))
    return fig


def fig_combo_mensal_ano(d: dict, mes_sel: int | None, ano: int) -> go.Figure:
    labels = [f"{m}/{ano}" for m in MESES]
    despesas = d["despesa_mes"]
    receitas = d["receita_mes"]
    colors = [C_ACCENT if mes_sel is not None and i == mes_sel else C_REAL for i in range(12)]
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(name="Despesa realizada", x=labels, y=despesas, marker_color=colors),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            name="Receita",
            x=labels,
            y=receitas,
            mode="lines+markers",
            line=dict(color=C_REC, width=2),
            marker=dict(size=6),
        ),
        secondary_y=True,
    )
    fig.update_layout(
        barmode="group",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=380,
        margin=dict(l=8, r=8, t=36, b=8),
        font=dict(color=C_TEXT),
        xaxis=dict(showgrid=False),
        yaxis=dict(title="Despesas (R$)", gridcolor=C_BORDER),
        yaxis2=dict(title="Receita (R$)", overlaying="y", side="right", showgrid=False),
    )
    return fig


def fig_combo_mensal(df: pd.DataFrame) -> go.Figure:
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(name="Despesa realizada", x=df["Mês"], y=df["Despesa realizada"], marker_color=C_REAL),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            name="Receita",
            x=df["Mês"],
            y=df["Receita"],
            mode="lines+markers",
            line=dict(color=C_REC, width=3),
            marker=dict(size=7),
        ),
        secondary_y=True,
    )
    fig.update_layout(
        barmode="group",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=380,
        margin=dict(l=8, r=8, t=36, b=8),
        font=dict(color=C_TEXT),
        xaxis=dict(showgrid=False),
        yaxis=dict(title="Despesas (R$)", gridcolor=C_BORDER),
        yaxis2=dict(title="Receita (R$)", overlaying="y", side="right", showgrid=False),
    )
    return fig


def fig_donut_categorias(
    cat_df: pd.DataFrame,
    total_periodo: float,
    periodo_txt: str,
    cores: list[str] | None = None,
) -> go.Figure:
    cores = cores or cores_departamentos(len(cat_df))
    nomes = cat_df["Categoria"].tolist()
    valores = cat_df["Realizado"].tolist()
    fig = go.Figure(
        go.Pie(
            labels=nomes,
            values=valores,
            hole=0.62,
            marker=dict(colors=cores),
            textinfo="none",
            hovertemplate="%{label}<br>%{value:,.2f}<br>%{percent}<extra></extra>",
        )
    )
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        height=220,
        margin=dict(l=4, r=4, t=4, b=4),
        showlegend=False,
        annotations=[
            dict(
                text=f"<b>{periodo_txt}</b><br>{br_moeda(total_periodo)}",
                x=0.5,
                y=0.5,
                font_size=11,
                font_color=C_MUTED,
                showarrow=False,
                align="center",
            )
        ],
    )
    return fig


def fig_spark_resultado(meses: list[str], valores: list[float]) -> go.Figure:
    cor = C_OK if valores and valores[-1] >= 0 else C_ALERT
    fig = go.Figure(go.Scatter(x=meses, y=valores, fill="tozeroy", mode="lines", line=dict(color=cor, width=2)))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        height=120,
        margin=dict(l=0, r=0, t=0, b=0),
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        showlegend=False,
    )
    return fig


@st.cache_data(show_spinner=False)
def carregar(mtime: float, path: str) -> dict:
    return snapshot_dados(Path(path))


def _executar_sync(planilha: Path) -> None:
    ano_s, _ = carregar_cadastro(planilha)
    with st.spinner("Atualizando planilha e Omie…"):
        res = forcar_atualizacao(planilha, ano_s, usar_omie=True)
    st.cache_data.clear()
    for msg in res.mensagens:
        if res.ok:
            st.toast(msg, icon="✅")
        else:
            st.toast(msg, icon="⚠️")
    if res.ok:
        st.session_state["ultima_sync_msg"] = " · ".join(res.mensagens)
    else:
        st.session_state["ultima_sync_msg"] = " · ".join(res.mensagens)


def main(*, embutido: bool = False) -> None:
    """embutido=True: dentro do app unificado (faturamentojca) — sem set_page_config nem senha própria."""
    if not embutido:
        st.set_page_config(page_title=TITULO_PAINEL, page_icon="📟", layout="wide")
    inject_css()
    if embutido:
        # No app unificado o cabeçalho já tem MATRIZ|FILIAL|OLARIA; evita o título gigante e a sidebar.
        st.markdown(
            """<style>
            [data-testid="stSidebar"]{display:none}
            [data-testid="stHorizontalBlock"]:has(.titulo-painel){
                background:transparent!important;border:0!important;box-shadow:none!important;
                padding:.2rem 0 .55rem!important;margin:0!important;
            }
            .titulo-painel{font-size:1.05rem!important;font-weight:600!important;color:#8B9BB4!important}
            .periodo-banner{font-size:1.15rem!important;margin-top:.35rem!important;padding-top:.35rem!important}
            </style>""",
            unsafe_allow_html=True,
        )

    if not embutido and not acesso_autorizado():
        return

    path = PLANILHA_PADRAO
    if not path.exists():
        st.error(f"Planilha não encontrada: {path}")
        return

    if "refresh_pending" not in st.session_state:
        st.session_state.refresh_pending = False
    if "last_omie_auto" not in st.session_state:
        st.session_state.last_omie_auto = 0.0

    if not embutido:
        with st.sidebar:
            st.markdown("### Atualização")
            auto = st.slider("Recarregar painel (s)", 0, 120, 30, 5, key="olaria_auto")
            omie_auto = st.slider("Sincronizar Omie (min, 0=off)", 0, 120, 0, 5, key="olaria_omie_auto")
            if auto > 0 and st_autorefresh:
                st_autorefresh(interval=auto * 1000, key="olaria_refresh")
            if omie_auto > 0 and time.time() - st.session_state.last_omie_auto >= omie_auto * 60:
                _executar_sync(path)
                st.session_state.last_omie_auto = time.time()
            st.markdown("---")
            st.markdown("**Somente leitura**")
            st.caption(f"Base: `{path.name}`")
            if credenciais_configuradas():
                st.caption("Omie: credenciais OK · sync em Faturamento (receitas).")
            else:
                st.caption("Omie: configure secrets `[omie]` se quiser sincronizar receitas.")
            st.caption("Despesas: aba Lançamentos no Excel.")

    hc, hb = st.columns([5.2, 1.15], vertical_alignment="center")
    with hc:
        titulo = "Custos · Galpão Olaria" if embutido else TITULO_PAINEL
        st.markdown(f'<h1 class="titulo-painel">{titulo}</h1>', unsafe_allow_html=True)
    with hb:
        if st.button("Atualizar dados", type="primary", use_container_width=True, key="btn_atualizar_header"):
            st.session_state.refresh_pending = True

    if st.session_state.refresh_pending:
        st.session_state.refresh_pending = False
        _executar_sync(path)
        st.rerun()

    if msg := st.session_state.pop("ultima_sync_msg", None):
        st.info(msg)

    try:
        d = carregar(mtime_planilha(path), str(path))
    except PermissionError:
        st.error("Feche o Excel (`CUSTOS OLARIA.xlsx`) e clique em **Atualizar dados**.")
        return
    except Exception as e:
        st.error(f"Erro ao carregar a planilha: {type(e).__name__}")
        return

    ano = d["ano"]
    mes_padrao = min(datetime.now().month - 1, 11)
    todas_cats = sorted(set(CATEGORIAS_PADRAO + list(d["por_categoria_ano"].keys())))
    if embutido:
        cats_sel = []
    else:
        cats_sel = st.sidebar.multiselect(
            "Filtrar categorias (opcional)", todas_cats, default=[], key="olaria_cats"
        )

    with st.container(border=True):
        st.markdown(
            '<span class="filtro-card-root" aria-hidden="true"></span>'
            '<p class="filtro-hint">Selecione o <strong>ano</strong> e o <strong>mês</strong> '
            "(ou <strong>Ano</strong> para ver o total anual).</p>",
            unsafe_allow_html=True,
        )
        if embutido:
            fa, fm, fc, fat = st.columns([1.1, 6.5, 2.6, 1.3], gap="medium")
        else:
            fa, fm = st.columns([1.35, 10], gap="medium")
            fc = fat = None
        opcoes_mes = ["Ano", *MESES]
        with fa:
            st.markdown('<p class="filtro-label">Ano</p>', unsafe_allow_html=True)
            st.pills("Ano", [ano], default=ano, key="filtro_ano", label_visibility="collapsed")
        with fm:
            st.markdown('<p class="filtro-label">Mês / período</p>', unsafe_allow_html=True)
            sel_periodo = st.pills(
                "Meses",
                opcoes_mes,
                default=MESES[mes_padrao],
                key="filtro_mes",
                label_visibility="collapsed",
            )
        if embutido and fc is not None:
            with fc:
                st.markdown('<p class="filtro-label">Categorias</p>', unsafe_allow_html=True)
                cats_sel = st.multiselect(
                    "Categorias", todas_cats, default=[], key="olaria_cats", label_visibility="collapsed"
                )
            with fat:
                st.markdown('<p class="filtro-label">&nbsp;</p>', unsafe_allow_html=True)
                st.caption("Somente leitura")

        if not sel_periodo:
            sel_periodo = MESES[mes_padrao]

        periodo_txt = f"Ano {ano}" if sel_periodo == "Ano" else f"{sel_periodo}/{ano}"
        st.markdown(
            f'<p class="periodo-banner">Período: {periodo_txt}</p>',
            unsafe_allow_html=True,
        )

    ver_ano_completo = sel_periodo == "Ano"
    if ver_ano_completo:
        idx = list(range(12))
        mes_destaque = mes_padrao
        receita_per = d["receita_ano"]
        despesa_per = d["despesa_ano"]
        media_per = d["media_despesa_mes"]
        mes_sel_chart: int | None = None
    else:
        mes_destaque = MESES.index(sel_periodo)
        idx = [mes_destaque]
        receita_per = d["receita_mes"][mes_destaque]
        despesa_per = d["despesa_mes"][mes_destaque]
        media_per = despesa_per
        mes_sel_chart = mes_destaque

    periodo_txt = f"Ano {ano}" if ver_ano_completo else f"{sel_periodo}/{ano}"

    resultado_per = receita_per - despesa_per
    n_meses = len(idx)

    des_m = d["despesa_mes"][mes_destaque]
    rec_m = d["receita_mes"][mes_destaque]
    despesa_ano = d["despesa_ano"]
    if ver_ano_completo:
        pct_mes_no_periodo = 100.0
    else:
        pct_mes_no_periodo = (100.0 * despesa_per / despesa_ano) if despesa_ano else 0.0

    por_cat = totais_por_categoria_periodo(d, idx, cats_sel or None)
    mes_nome = MESES[mes_destaque]

    teto_per = TETO_GASTOS_MENSAL * n_meses
    limite_disponivel = teto_per - despesa_per
    pct_uso_teto = (100.0 * despesa_per / teto_per) if teto_per else 0.0
    media_planilha = d["media_despesa_mes"]

    k1, k2, k3, k4 = st.columns(4, gap="medium")
    with k1:
        sub_teto = f"{periodo_txt} · {n_meses}× R$ 50 mil" if ver_ano_completo else "Teto mensal de referência"
        st.markdown(
            html_medidor("Teto de gastos", br_moeda(teto_per), sub_teto, C_MUTED),
            unsafe_allow_html=True,
        )
    with k2:
        cor_lim = C_OK if limite_disponivel >= 0 else C_ALERT
        sub_lim = f"Despesa {br_moeda(despesa_per)} · {br_num(pct_uso_teto)} % do teto"
        st.markdown(
            html_medidor("Limite disponível", br_moeda(limite_disponivel), sub_lim, cor_lim),
            unsafe_allow_html=True,
        )
    with k3:
        rot_res = "Gasto no ano" if ver_ano_completo else "Resultado do mês"
        acima_teto = despesa_per > teto_per
        cor_res = C_ALERT if acima_teto else C_OK
        if acima_teto:
            valor_res = -(despesa_per - teto_per)
            sub_res = f"Total gasto {br_moeda(despesa_per)} · acima do teto {br_moeda(teto_per)}"
        else:
            valor_res = despesa_per
            sub_res = f"Despesa realizada · teto {br_moeda(teto_per)}"
        st.markdown(
            html_medidor(rot_res, br_moeda(valor_res), sub_res, cor_res),
            unsafe_allow_html=True,
        )
    with k4:
        st.markdown(
            html_medidor("Média mensal", br_moeda(media_planilha), "Despesas · média da planilha", C_ACCENT),
            unsafe_allow_html=True,
        )

    por_cat_pos = {k: v for k, v in por_cat.items() if v > 0}
    cat_df = None
    if por_cat_pos:
        cat_df = pd.DataFrame([{"Categoria": k, "Realizado": v} for k, v in por_cat_pos.items()])
        cat_df = cat_df.sort_values("Realizado", ascending=False)

    g1, g2 = st.columns(2, gap="medium")
    max_mes_ano = max(d["despesa_mes"]) if any(d["despesa_mes"]) else 1.0
    gauge_val = despesa_per if ver_ano_completo else des_m
    gauge_tit = f"Despesas · {periodo_txt}" if ver_ano_completo else f"Despesa · {sel_periodo}/{ano}"
    with g1:
        with st.container(border=True):
            st.markdown('<p class="md-card-title">Medidor · despesas</p>', unsafe_allow_html=True)
            st.plotly_chart(
                fig_gauge_valor(gauge_tit, gauge_val, max_mes_ano, C_REAL),
                use_container_width=True,
                config={"displayModeBar": False},
            )
    with g2:
        with st.container(border=True):
            st.markdown('<p class="md-card-title">Participação no ano</p>', unsafe_allow_html=True)
            if ver_ano_completo:
                pct_gauge_tit = "Ano completo"
            else:
                pct_gauge_tit = f"{sel_periodo}/{ano} no ano"
            st.plotly_chart(
                fig_gauge_pct(pct_gauge_tit, pct_mes_no_periodo, C_ACCENT),
                use_container_width=True,
                config={"displayModeBar": False},
            )

    if cat_df is not None:
        cores_dep = cores_departamentos(len(cat_df))
        with st.container(border=True):
            st.markdown(
                f'<p class="md-card-title">Composição por departamento · {periodo_txt}</p>',
                unsafe_allow_html=True,
            )
            fig_col, leg_col = st.columns([1, 1.35], gap="large")
            with fig_col:
                st.plotly_chart(
                    fig_donut_categorias(cat_df, despesa_per, periodo_txt, cores_dep),
                    use_container_width=True,
                    config={"displayModeBar": False},
                )
            with leg_col:
                st.markdown(
                    html_lista_departamentos(cat_df, despesa_per, cores_dep),
                    unsafe_allow_html=True,
                )
            det_dep = despesas_por_departamento_periodo(d, idx, cats_sel or None)
            if det_dep:
                tb_dep = pd.DataFrame(det_dep).sort_values(["Departamento", "Total"], ascending=[True, False])
                tb_dep["Total (R$)"] = tb_dep["Total"].apply(br_moeda)
                with st.expander("Detalhe por despesa (linha a linha)", expanded=False):
                    st.dataframe(
                        tb_dep[["Departamento", "Despesa", "Total (R$)"]],
                        use_container_width=True,
                        hide_index=True,
                    )

    labels = [MESES[i] for i in idx]
    df_mes = pd.DataFrame(
        {
            "Mês": labels,
            "Receita": [d["receita_mes"][i] for i in idx],
            "Despesa realizada": [d["despesa_mes"][i] for i in idx],
            "Resultado": [d["receita_mes"][i] - d["despesa_mes"][i] for i in idx],
        }
    )
    with st.container(border=True):
        st.markdown('<p class="md-card-title">Série temporal · despesas x receita</p>', unsafe_allow_html=True)
        if ver_ano_completo:
            st.plotly_chart(fig_combo_mensal(df_mes), use_container_width=True, config={"displayModeBar": False})
        else:
            st.plotly_chart(
                fig_combo_mensal_ano(d, mes_sel_chart, ano),
                use_container_width=True,
                config={"displayModeBar": False},
            )

    c_sp, c_info = st.columns([2, 1])
    with c_sp:
        st.plotly_chart(
            fig_spark_resultado(df_mes["Mês"].tolist(), df_mes["Resultado"].tolist()),
            use_container_width=True,
            config={"displayModeBar": False},
        )
    with c_info:
        if ver_ano_completo:
            st.markdown(
                f"**{periodo_txt}**  \n"
                f"Receita: **{br_moeda(receita_per)}**  \n"
                f"Despesa: **{br_moeda(despesa_per)}**  \n"
                f"Saldo: **{br_moeda(resultado_per)}**  \n"
                f"Média/mês: **{br_moeda(media_per)}**"
            )
        else:
            st.markdown(
                f"**{sel_periodo}/{ano}**  \n"
                f"Receita: **{br_moeda(rec_m)}**  \n"
                f"Despesa: **{br_moeda(des_m)}**  \n"
                f"Saldo: **{br_moeda(rec_m - des_m)}**  \n"
                f"Parte do ano: **{br_num(pct_mes_no_periodo)}%**  \n"
                f"Total ano: **{br_moeda(despesa_ano)}**"
            )

    tab_det, tab_cad = st.tabs(["Detalhe por despesa", "Cadastro (consulta)"])

    with tab_det:
        alvo = periodo_txt if ver_ano_completo else f"{sel_periodo}/{ano}"
        st.markdown(
            f'<p class="periodo-detalhe">Despesas com valor · <strong>{alvo}</strong></p>',
            unsafe_allow_html=True,
        )
        linhas = []
        meses_det = idx if ver_ano_completo else [mes_destaque]
        for nome, cat, real in zip(d["despesas"], d["categorias"], d["realizado"]):
            if cats_sel and cat not in cats_sel:
                continue
            if ver_ano_completo:
                total = sum(real[i] for i in meses_det)
                if total == 0:
                    continue
                linhas.append({"Despesa": nome, "Categoria": cat, "Realizado": total})
            else:
                r = real[mes_destaque]
                if r == 0:
                    continue
                linhas.append({"Despesa": nome, "Categoria": cat, "Realizado": r})
        if linhas:
            tb = pd.DataFrame(linhas).sort_values("Realizado", ascending=False)
            st.dataframe(
                tb.style.format({"Realizado": br_moeda}, na_rep="—"),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("Nenhuma despesa com valor neste mês / filtro.")
        fmt_mes = {
            "Receita": br_moeda,
            "Despesa realizada": br_moeda,
            "Resultado": br_moeda,
        }
        st.dataframe(
            df_mes.style.format(fmt_mes, na_rep="—"),
            use_container_width=True,
            hide_index=True,
        )

    with tab_cad:
        st.caption("Referência do cadastro fixo — alterações somente na aba **Cadastro** do Excel.")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Despesa": x.nome,
                        "Categoria": x.categoria,
                        "Valor": x.valor,
                        "Periodicidade": x.periodicidade,
                    }
                    for x in d["cadastro"]
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )


if __name__ == "__main__":
    main()
