"""App Streamlit: o mesmo painel do localhost:8000.

Fontes de dados, nesta ordem:
- snapshot: PAINEL_DATA_URL + PAINEL_DATA_KEY → arquivo criptografado publicado pelo GitHub Actions
  (scripts/publicar_dados.py). As chaves da Omie não ficam no Streamlit.
- omie: OMIE_FILIAL_APP_KEY + OMIE_FILIAL_APP_SECRET → consulta direta da filial (somente leitura).
- sample: dados fictícios (backend/data/vendas_demo.json).

Senha: APP_PASSWORD_HASH (gerado por scripts/gerar_secrets.py); a senha em si não fica guardada.
"""
import gzip
import hashlib
import hmac
import json
import os
import time
from datetime import date, datetime, timedelta
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
# empresa → arquivo publicado por scripts/publicar_dados.py no mesmo branch de PAINEL_DATA_URL
ARQUIVOS = {"Filial": "painel.enc", "Matriz": "painel_matriz.enc"}
if os.getenv("PAINEL_DATA_URL") and os.getenv("PAINEL_DATA_KEY"):
    FONTE = "snapshot"
elif os.getenv("OMIE_FILIAL_APP_KEY") and os.getenv("OMIE_FILIAL_APP_SECRET"):
    FONTE = "omie"
else:
    FONTE = "sample"

st.set_page_config(page_title="Vendas · JCA", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""<style>
header[data-testid="stHeader"]{display:none}
.block-container{padding:.6rem 1rem 0;max-width:100%}
div[data-testid="stHorizontalBlock"]{align-items:end}
iframe{border-radius:12px}
</style>""", unsafe_allow_html=True)


MAX_TENTATIVAS, ESPERA_BLOQUEIO = 5, 300


def senha_confere(tentativa: str) -> bool:
    guardado = os.getenv("APP_PASSWORD_HASH", "")
    if guardado:
        try:
            _, iteracoes, sal, alvo = guardado.split("$")
            calc = hashlib.pbkdf2_hmac("sha256", tentativa.encode(), bytes.fromhex(sal), int(iteracoes)).hex()
        except ValueError:
            return False
        return hmac.compare_digest(calc, alvo)
    return hmac.compare_digest(tentativa.encode(), os.getenv("APP_PASSWORD", "").encode())


def exigir_senha() -> None:
    if not (os.getenv("APP_PASSWORD_HASH") or os.getenv("APP_PASSWORD")) or st.session_state.get("ok"):
        return
    with st.form("login"):
        st.subheader("Painel de vendas · JCA")
        tentativa = st.text_input("Senha", type="password")
        if st.form_submit_button("Entrar"):
            restante = st.session_state.get("bloqueio", 0) - time.time()
            if restante > 0:
                st.error(f"Muitas tentativas. Tente de novo em {int(restante // 60) + 1} min.")
            elif senha_confere(tentativa):
                st.session_state.update(ok=True, erros=0)
                st.rerun()
            else:
                time.sleep(1.5)
                erros = st.session_state.get("erros", 0) + 1
                st.session_state["erros"] = erros
                if erros >= MAX_TENTATIVAS:
                    st.session_state.update(erros=0, bloqueio=time.time() + ESPERA_BLOQUEIO)
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
    fim_p = date(di.year, 3 * ((di.month - 1) // 3) + 1, 1) - timedelta(days=1)
    return date(fim_p.year, 3 * ((fim_p.month - 1) // 3) + 1, 1).isoformat(), fim_p.isoformat()


class ErroSnapshot(RuntimeError):
    pass


@st.cache_data(ttl=300, show_spinner=False)
def snapshot(empresa: str = "Filial") -> dict:
    import httpx
    from cryptography.fernet import Fernet, InvalidToken

    url = os.environ["PAINEL_DATA_URL"].strip().strip('"')
    url = url.rsplit("/", 1)[0] + "/" + ARQUIVOS[empresa]
    chave = os.environ["PAINEL_DATA_KEY"].strip().strip('"').replace(" ", "")
    try:
        r = httpx.get(url, params={"t": int(time.time() // 300)}, timeout=60, follow_redirects=True)
    except httpx.HTTPError:
        raise ErroSnapshot("Não foi possível baixar os dados (falha de rede). Tente de novo em instantes.")
    if r.status_code == 404 and empresa != "Filial":
        raise ErroSnapshot(f"Os dados da {empresa} ainda não foram publicados. Tente de novo em alguns minutos.")
    if r.status_code != 200:
        raise ErroSnapshot(f"Download dos dados falhou (HTTP {r.status_code}). Confira PAINEL_DATA_URL.")
    try:
        f = Fernet(chave.encode())
    except ValueError:
        raise ErroSnapshot(f"PAINEL_DATA_KEY em formato inválido ({len(chave)} caracteres; o correto são 44, "
                           "terminando com '='). Copie de novo do .env.")
    try:
        return json.loads(gzip.decompress(f.decrypt(r.content)))
    except InvalidToken:
        raise ErroSnapshot("PAINEL_DATA_KEY não corresponde à chave usada na publicação. Copie de novo do .env.")


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
if FONTE == "sample":
    st.warning("Dados FICTÍCIOS de demonstração. Para ver as vendas reais, cadastre PAINEL_DATA_URL e "
               "PAINEL_DATA_KEY em Settings > Secrets do app.")

hoje = date.today()
c0, c1, c1b, c1c, c2, c3, c4 = st.columns([1.4, 1.1, 1.1, 2.4, 1.1, 1.4, 2.4])
empresa = "Filial"
if FONTE == "snapshot":
    with c0:
        empresa = st.segmented_control("Empresa", list(ARQUIVOS), default="Filial", key="empresa") or "Filial"
snap = None
if FONTE == "snapshot":
    try:
        with st.spinner("Carregando dados…"):
            snap = snapshot(empresa)
            EMPRESA = snap.get("empresa") or f"JCA {empresa}"
    except ErroSnapshot as e:
        st.error(str(e))
        st.stop()
    except Exception as e:
        st.error(f"Não foi possível carregar os dados publicados ({type(e).__name__}).")
        st.stop()
    lim_ini, lim_fim = date.fromisoformat(snap["inicio"]), date.fromisoformat(snap["fim"])
    padrao = (max(date.fromisoformat(snap.get("inicio_padrao", snap["inicio"])), lim_ini), lim_fim)
elif FONTE == "omie":
    lim_ini, lim_fim = None, hoje
    padrao = (inicio_padrao(hoje), hoje)
else:
    lim_ini, lim_fim = date(2026, 7, 1), date(2026, 9, 30)
    padrao = (lim_ini, lim_fim)

# Período digitado (DD/MM/AAAA); o calendário de intervalo do Streamlit recarrega a página no meio da seleção.
ATALHOS = ("Mês atual", "Mês anterior", "Trimestre")


def _br(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def _ler_data(txt: str) -> date | None:
    try:
        return datetime.strptime((txt or "").strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


def _aplicar_atalho(lim_ini: date | None, lim_fim: date) -> None:
    tipo = st.session_state.get("atalho")
    fim_a = lim_fim
    if tipo == "Mês atual":
        ini_a = fim_a.replace(day=1)
    elif tipo == "Mês anterior":
        fim_a = fim_a.replace(day=1) - timedelta(days=1)
        ini_a = fim_a.replace(day=1)
    elif tipo == "Trimestre":
        ini_a = date(fim_a.year, 3 * ((fim_a.month - 1) // 3) + 1, 1)
    else:
        return
    if lim_ini:
        ini_a, fim_a = max(ini_a, lim_ini), max(fim_a, lim_ini)
    st.session_state.update(de=_br(ini_a), ate=_br(fim_a), atalho=None)


# Troca de empresa muda os limites; reinicia o período no padrão dela.
if st.session_state.get("per_empresa") != empresa or "de" not in st.session_state:
    st.session_state.update(de=_br(padrao[0]), ate=_br(padrao[1]), per_empresa=empresa)
with c1:
    st.text_input("De", key="de", placeholder="DD/MM/AAAA", max_chars=10)
with c1b:
    st.text_input("Até", key="ate", placeholder="DD/MM/AAAA", max_chars=10)
with c1c:
    st.segmented_control("Atalhos", ATALHOS, key="atalho", on_change=_aplicar_atalho, args=(lim_ini, lim_fim))

d_ini, d_fim = _ler_data(st.session_state["de"]), _ler_data(st.session_state["ate"])
if not d_ini or not d_fim:
    st.warning("Data inválida. Digite no formato DD/MM/AAAA, por exemplo 01/10/2026.")
    st.stop()
if d_ini > d_fim:
    st.warning("A data inicial (De) é maior que a final (Até).")
    st.stop()
ajuste = []
if lim_ini and d_ini < lim_ini:
    d_ini = lim_ini
    ajuste.append(f"início ajustado para {_br(lim_ini)}, primeiro dia com dados")
if d_fim > lim_fim:
    d_fim = lim_fim
    ajuste.append(f"fim ajustado para {_br(lim_fim)}, último dia com dados")
if d_ini > d_fim:
    st.warning(f"Não há dados nesse período. Os dados vão de {_br(lim_ini) if lim_ini else '—'} a {_br(lim_fim)}.")
    st.stop()
if ajuste:
    st.caption("Período " + "; ".join(ajuste) + ".")
inicio, fim = d_ini.isoformat(), d_fim.isoformat()
with c2:
    if st.button("Atualizar dados", use_container_width=True):
        for f in (snapshot, vendas, estoque):
            f.clear()
        st.rerun()
p_ini, p_fim = periodo_anterior(inicio, fim)

if snap is not None:
    rows = [r for r in snap["rows"] if inicio <= r["d"] <= fim]
    rows_prev = [r for r in snap["rows"] if p_ini <= r["d"] <= p_fim] if p_ini >= snap["inicio"] else []
    est = snap.get("estoque") if fim == snap["fim"] else None
    atualizado, fonte_painel, fonte_txt = snap["gerado_em"], "omie", "Omie (atualização automática)"
    hist, hist_ini, hist_fim = snap["rows"], snap["inicio"], snap["fim"]
else:
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
    fonte_painel = FONTE
    fonte_txt = "Omie" if FONTE == "omie" else "dados fictícios de demonstração"
    hist, hist_ini, hist_fim = rows_prev + rows, (p_ini if rows_prev else inicio), fim

# PDV/NFC-e só na Filial; o flag vai no HTML para o filtro/gráfico sumirem na Matriz.
tem_pdv = empresa == "Filial"
if tem_pdv is False:
    rows = [r for r in rows if r.get("ch") != "PDV"]
    rows_prev = [r for r in rows_prev if r.get("ch") != "PDV"]
    hist = [r for r in hist if r.get("ch") != "PDV"]
# Histórico completo vai junto para a seção Relatório (comparativos e previsão).
extra = {"tem_pdv": tem_pdv, "hist": hist, "hist_inicio": hist_ini, "hist_fim": hist_fim}
html_app = painel.montar_html(rows, rows_prev, inicio, fim, p_ini, p_fim, EMPRESA, atualizado, fonte_painel, est,
                              modo="app", **extra)
html_rel = painel.montar_html(rows, rows_prev, inicio, fim, p_ini, p_fim, EMPRESA, atualizado, fonte_painel, est,
                              **extra)
with c3:
    st.download_button("Baixar relatório (HTML)", html_rel, use_container_width=True,
                       file_name=f"Relatorio_Vendas_{EMPRESA.replace(' ', '_')}_{inicio}_a_{fim}.html", mime="text/html")
with c4:
    comp = f" · comparativo {relatorio.dbr(p_ini)} a {relatorio.dbr(p_fim)}" if rows_prev else ""
    st.caption(f"Fonte: {fonte_txt} · dados de {atualizado}{comp}")

if hasattr(st, "iframe"):
    st.iframe(html_app, height=1000)
else:
    components.html(html_app, height=1000, scrolling=True)
