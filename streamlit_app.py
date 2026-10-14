"""App Streamlit: o mesmo painel do localhost:8000, com dados da Omie (somente leitura).

Credenciais vêm de st.secrets (Streamlit Cloud) ou do .env local; nunca vão para o navegador.
Sem credenciais, o app abre com dados fictícios (backend/data/vendas_demo.json).
"""
import json
import os
import time
from datetime import date, timedelta
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
try:
    for _k, _v in st.secrets.items():
        if isinstance(_v, (str, int, float)):
            os.environ[_k] = str(_v)
except Exception:  # sem secrets.toml (execução local)
    pass

from backend.app import omie, painel, relatorio  # noqa: E402  (depois de carregar as credenciais)

EMPRESA = os.getenv("OMIE_EMPRESA", "JCA Filial")
FONTE = "omie" if os.getenv("OMIE_APP_KEY") and os.getenv("OMIE_APP_SECRET") else "sample"

st.set_page_config(page_title=f"Vendas · {EMPRESA}", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""<style>
header[data-testid="stHeader"]{display:none}
.block-container{padding:.6rem 1rem 0;max-width:100%}
div[data-testid="stHorizontalBlock"]{align-items:end}
iframe{border-radius:12px}
</style>""", unsafe_allow_html=True)


def exigir_senha() -> None:
    senha = os.getenv("APP_PASSWORD")
    if not senha or st.session_state.get("ok"):
        return
    with st.form("login"):
        st.subheader(f"Painel de vendas · {EMPRESA}")
        tentativa = st.text_input("Senha", type="password")
        if st.form_submit_button("Entrar"):
            if tentativa == senha:
                st.session_state["ok"] = True
                st.rerun()
            st.error("Senha incorreta.")
    st.stop()


def inicio_padrao(hoje: date) -> date:
    v = os.getenv("DEFAULT_INICIO", "trimestre").strip().lower()
    if v == "mes":
        return hoje.replace(day=1)
    if v == "trimestre":
        return date(hoje.year, 3 * ((hoje.month - 1) // 3) + 1, 1)
    return date.fromisoformat(v)


def periodo_anterior(inicio: str, fim: str) -> tuple[str, str]:
    """Um mês → mês anterior; período maior → trimestre anterior ao início (como o painel local)."""
    di = date.fromisoformat(inicio)
    if di.day == 1 and inicio[:7] == fim[:7]:
        return relatorio.periodo_comparacao(inicio, fim)
    q = 3 * ((di.month - 1) // 3) + 1
    ini_q = date(di.year, q, 1)
    fim_p = ini_q - timedelta(days=1)
    return date(fim_p.year, 3 * ((fim_p.month - 1) // 3) + 1, 1).isoformat(), fim_p.isoformat()


def _buscar(inicio: str, fim: str):
    if FONTE == "omie":
        return omie.vendas(inicio, fim), time.time()
    rows = json.loads((ROOT / "backend/data/vendas_demo.json").read_text(encoding="utf-8"))
    return [r for r in rows if inicio <= r["d"] <= fim], time.time()


@st.cache_data(ttl=600, show_spinner=False)
def vendas(inicio: str, fim: str):
    return _buscar(inicio, fim)


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def vendas_fechado(inicio: str, fim: str):
    return _buscar(inicio, fim)


@st.cache_data(ttl=3600, show_spinner=False)
def estoque():
    return omie.estoque_atual() if FONTE == "omie" else None


exigir_senha()

hoje = date.today()
padrao = (inicio_padrao(hoje), hoje) if FONTE == "omie" else (date(2026, 7, 1), date(2026, 9, 30))
c1, c2, c3, c4 = st.columns([3, 1.2, 1.6, 4])
with c1:
    per = st.date_input("Período", value=padrao, max_value=hoje, format="DD/MM/YYYY")
if not isinstance(per, (list, tuple)) or len(per) != 2:
    st.info("Selecione a data inicial e a final.")
    st.stop()
inicio, fim = per[0].isoformat(), per[1].isoformat()
with c2:
    if st.button("Atualizar dados", use_container_width=True):
        vendas.clear()
        estoque.clear()
p_ini, p_fim = periodo_anterior(inicio, fim)

try:
    with st.spinner("Consultando a Omie (a primeira carga pode levar alguns minutos)…"):
        rows, ts = (vendas if fim >= hoje.isoformat() else vendas_fechado)(inicio, fim)
        rows_prev, _ = vendas_fechado(p_ini, p_fim)
        est = estoque() if fim >= hoje.isoformat() else None
except omie.OmieBloqueada:
    st.warning("A Omie bloqueou temporariamente as consultas por excesso de chamadas. Tente de novo em alguns minutos.")
    st.stop()
except Exception:  # nunca exibir detalhes que possam conter credenciais
    st.error("Não foi possível consultar a fonte de dados.")
    st.stop()

atualizado = time.strftime("%d/%m/%Y %H:%M", time.localtime(ts))
fonte_txt = "Omie" if FONTE == "omie" else "dados fictícios de demonstração"
html_app = painel.montar_html(rows, rows_prev, inicio, fim, p_ini, p_fim, EMPRESA, atualizado, FONTE, est, modo="app")
html_rel = painel.montar_html(rows, rows_prev, inicio, fim, p_ini, p_fim, EMPRESA, atualizado, FONTE, est)
with c3:
    st.download_button("Baixar relatório (HTML)", html_rel, use_container_width=True,
                       file_name=f"Relatorio_Vendas_{EMPRESA.replace(' ', '_')}_{inicio}_a_{fim}.html", mime="text/html")
with c4:
    st.caption(f"Fonte: {fonte_txt} · dados de {atualizado} · comparativo {relatorio.dbr(p_ini)} a {relatorio.dbr(p_fim)}")

if hasattr(st, "iframe"):
    st.iframe(html_app, height=1000)
else:
    components.html(html_app, height=1000, scrolling=True)
