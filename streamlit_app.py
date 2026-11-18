"""App unificado JCA: MATRIZ | FILIAL | OLARIA no mesmo link (faturamentojca.streamlit.app).

Em Matriz e Filial: Faturamento e Financeiro (dados publicados cifrados no GitHub).
Em Olaria: painel de custos do galpão (planilha em olária/data).

Senha: APP_PASSWORD_HASH (uma só para o app unificado).
"""
import gzip
import hashlib
import hmac
import json
import os
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

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

from backend.app import omie, painel, relatorio  # noqa: E402

EMPRESAS = ("MATRIZ", "FILIAL", "OLARIA")
URL_FILIAL = "https://raw.githubusercontent.com/lelisson/FATURAMENTOLOJAJCA/dados/painel.enc"
URL_MATRIZ = "https://raw.githubusercontent.com/lelisson/FATURAMENTOMATRIZJCA/dados/painel.enc"

st.set_page_config(page_title="Painel · JCA", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""<style>
header[data-testid="stHeader"]{display:none}
.block-container{padding:.6rem 1rem 0;max-width:100%}
div[data-testid="stHorizontalBlock"]{align-items:end}
div[data-testid="stHorizontalBlock"]>div[data-testid="stColumn"]:first-child{flex:0 0 auto!important;width:auto!important;min-width:max-content!important;margin-right:.75rem}
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
        st.subheader("Painel · JCA")
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
    di = date.fromisoformat(inicio)
    if di.day == 1 and inicio[:7] == fim[:7]:
        return relatorio.periodo_comparacao(inicio, fim)
    fim_p = date(di.year, 3 * ((di.month - 1) // 3) + 1, 1) - timedelta(days=1)
    return date(fim_p.year, 3 * ((fim_p.month - 1) // 3) + 1, 1).isoformat(), fim_p.isoformat()


class ErroSnapshot(RuntimeError):
    pass


def _baixar(url: str, chave: str, nao_publicado: str | None = None) -> dict:
    import httpx
    from cryptography.fernet import Fernet, InvalidToken

    chave = chave.strip().strip('"').replace(" ", "")
    try:
        r = httpx.get(url, params={"t": int(time.time() // 300)}, timeout=60, follow_redirects=True)
    except httpx.HTTPError:
        raise ErroSnapshot("Não foi possível baixar os dados (falha de rede). Tente de novo em instantes.")
    if r.status_code == 404 and nao_publicado:
        raise ErroSnapshot(nao_publicado)
    if r.status_code != 200:
        raise ErroSnapshot(f"Download dos dados falhou (HTTP {r.status_code}). Confira a URL dos dados.")
    try:
        f = Fernet(chave.encode())
    except ValueError:
        raise ErroSnapshot(f"Chave de dados em formato inválido ({len(chave)} caracteres; o correto são 44, "
                           "terminando com '=').")
    try:
        return json.loads(gzip.decompress(f.decrypt(r.content)))
    except InvalidToken:
        raise ErroSnapshot("A chave de dados não corresponde à usada na publicação.")


@st.cache_data(ttl=300, show_spinner=False)
def snapshot(url: str, chave: str) -> dict:
    return _baixar(url, chave)


@st.cache_data(ttl=300, show_spinner=False)
def snapshot_financeiro(url: str, chave: str) -> dict:
    return _baixar(url.rsplit("/", 1)[0] + "/financeiro.enc", chave,
                   "O painel financeiro ainda não foi publicado. A primeira publicação sai na próxima "
                   "atualização automática (até 20 min).")


def _buscar(inicio: str, fim: str, fonte: str):
    if fonte == "omie":
        return omie.vendas(inicio, fim), time.time()
    rows = json.loads((ROOT / "backend/data/vendas_demo.json").read_text(encoding="utf-8"))
    return [r for r in rows if inicio <= r["d"] <= fim], time.time()


@st.cache_data(ttl=600, show_spinner=False)
def vendas(inicio: str, fim: str, fonte: str):
    return _buscar(inicio, fim, fonte)


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def vendas_fechado(inicio: str, fim: str, fonte: str):
    return _buscar(inicio, fim, fonte)


@st.cache_data(ttl=3600, show_spinner=False)
def estoque(fonte: str):
    return omie.estoque_atual() if fonte == "omie" else None


def cfg_empresa(nome: str) -> dict:
    """URL/chave/nome exibido e se tem PDV, conforme a empresa selecionada."""
    if nome == "MATRIZ":
        url = (os.getenv("PAINEL_MATRIZ_DATA_URL") or URL_MATRIZ).strip().strip('"')
        chave = (os.getenv("PAINEL_MATRIZ_DATA_KEY") or "").strip().strip('"')
        return {"url": url, "chave": chave, "empresa": "JCA Matriz", "tem_pdv": False,
                "arquivo": "Financeiro_JCA_Matriz"}
    url = (os.getenv("PAINEL_DATA_URL") or URL_FILIAL).strip().strip('"')
    chave = (os.getenv("PAINEL_DATA_KEY") or "").strip().strip('"')
    return {"url": url, "chave": chave, "empresa": "JCA Filial", "tem_pdv": True,
            "arquivo": "Financeiro_JCA_Filial"}


exigir_senha()

# ---------- seletor de empresa ----------
if st.session_state.get("empresa") not in EMPRESAS:
    st.session_state["empresa"] = st.session_state.get("empresa_atual", "FILIAL")
st.session_state["empresa_atual"] = st.session_state["empresa"]

# Período digitado (DD/MM/AAAA).
ATALHOS = ("Mês atual", "Mês anterior", "Trimestre")


def _br(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def _formatar_data(txt: str) -> str:
    dig = "".join(c for c in (txt or "") if c.isdigit())
    return f"{dig[:2]}/{dig[2:4]}/{dig[4:8]}" if len(dig) == 8 else (txt or "").strip()


def _ler_data(txt: str) -> date | None:
    try:
        return datetime.strptime(_formatar_data(txt), "%d/%m/%Y").date()
    except ValueError:
        return None


def _normalizar(chave: str) -> None:
    st.session_state[chave] = _formatar_data(st.session_state.get(chave, ""))


MASCARA_DATA = """<script>
(function(){
  const P = window.parent, doc = P.document;
  const codigo = `(function(){
    if (window.__mascaraData) return; window.__mascaraData = true;
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
    const fmt = v => { const d = v.replace(/\\\\D/g, '').slice(0, 8);
      return d.slice(0, 2) + (d.length > 2 ? '/' + d.slice(2, 4) : '') + (d.length > 4 ? '/' + d.slice(4) : ''); };
    const ligar = el => {
      if (el.dataset.mascara) return; el.dataset.mascara = '1';
      el.setAttribute('inputmode', 'numeric');
      el.addEventListener('input', () => {
        const novo = fmt(el.value);
        if (novo === el.value) return;
        setter.call(el, novo);
        el.setSelectionRange(novo.length, novo.length);
        el.dispatchEvent(new Event('input', { bubbles: true }));
      });
    };
    const varrer = () => document.querySelectorAll('input[aria-label="De"], input[aria-label="Até"]').forEach(ligar);
    varrer(); new MutationObserver(varrer).observe(document.body, { childList: true, subtree: true });
    const ajustarPainel = () => {
      const fs = [...document.querySelectorAll('iframe')].filter(f => f.offsetHeight > 300);
      if (!fs.length) return;
      const f = fs.reduce((a, b) => a.offsetHeight >= b.offsetHeight ? a : b);
      const h = Math.max(560, Math.floor(window.innerHeight - f.getBoundingClientRect().top - window.scrollY - 10));
      if (Math.abs(f.offsetHeight - h) > 2) { f.style.height = h + 'px'; f.setAttribute('height', h); }
    };
    window.addEventListener('resize', ajustarPainel); setInterval(ajustarPainel, 800); ajustarPainel();
  })();`;
  if (P.__mascaraData) return;
  const s = doc.createElement('script'); s.textContent = codigo; doc.head.appendChild(s);
  if (!P.__mascaraData) P.eval(codigo);
})();
</script>"""


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


PAGINAS = ("Faturamento", "Financeiro")
if st.session_state.get("pagina") not in PAGINAS:
    st.session_state["pagina"] = st.session_state.get("pagina_atual", PAGINAS[0])
st.session_state["pagina_atual"] = st.session_state["pagina"]
for _campo in ("de", "ate"):
    if _campo in st.session_state:
        st.session_state[_campo] = st.session_state[_campo]


def barra_empresa() -> None:
    st.segmented_control("Empresa", EMPRESAS, key="empresa")


def cabecalho(pesos: list[float]) -> list:
    """Empresa + Faturamento/Financeiro na primeira faixa; devolve as demais colunas."""
    cols = st.columns([1.8, 1.5, *pesos])
    with cols[0]:
        barra_empresa()
    with cols[1]:
        st.segmented_control("Painel", PAGINAS, key="pagina")
    return cols[2:]


def pagina_olaria() -> None:
    c0, = st.columns([1.8])
    with c0:
        barra_empresa()
    from olaria.app import main as olaria_main
    olaria_main(embutido=True)
    st.stop()


if st.session_state["empresa"] == "OLARIA":
    pagina_olaria()

cfg = cfg_empresa(st.session_state["empresa"])
EMPRESA = cfg["empresa"]
TEM_PDV = cfg["tem_pdv"]
tem_chave = bool(cfg["chave"])
if tem_chave:
    FONTE = "snapshot"
elif os.getenv("OMIE_FILIAL_APP_KEY") and os.getenv("OMIE_FILIAL_APP_SECRET") and st.session_state["empresa"] == "FILIAL":
    FONTE = "omie"
else:
    FONTE = "sample"

if FONTE == "sample":
    st.warning("Dados FICTÍCIOS de demonstração. Cadastre as chaves de dados em Settings > Secrets do app "
               "(PAINEL_DATA_KEY para a Filial e PAINEL_MATRIZ_DATA_KEY para a Matriz).")


def pagina_financeiro() -> None:
    f1, f2, f3 = cabecalho([1.1, 1.4, 6.0])
    if FONTE != "snapshot":
        st.info("O painel financeiro usa os dados publicados automaticamente. Cadastre as chaves em "
                "Settings > Secrets do app.")
        st.stop()
    try:
        with st.spinner("Carregando financeiro…"):
            fin = snapshot_financeiro(cfg["url"], cfg["chave"])
    except ErroSnapshot as e:
        st.error(str(e))
        st.stop()
    except Exception as e:
        st.error(f"Não foi possível carregar o financeiro publicado ({type(e).__name__}).")
        st.stop()
    from financeiro import pagina as fin_pagina

    with f1:
        if st.button("Atualizar dados", use_container_width=True):
            snapshot_financeiro.clear()
            st.rerun()
    with f2:
        st.download_button(
            "Baixar relatório (HTML)",
            fin_pagina.montar_html(fin, empresa=EMPRESA, tem_pdv=TEM_PDV),
            use_container_width=True,
            file_name=f"{cfg['arquivo']}_{fin['inicio']}_a_{fin['fim']}.html",
            mime="text/html",
        )
    with f3:
        gerado = datetime.fromtimestamp(fin["gerado_em"], ZoneInfo("America/Sao_Paulo"))
        st.caption(f"Atualizado em {gerado:%d/%m/%Y %H:%M} · "
                   f"período {_br(date.fromisoformat(fin['inicio']))} a {_br(date.fromisoformat(fin['fim']))}")
    components.html(MASCARA_DATA, height=0)
    html_fin = fin_pagina.montar_html(fin, app=True, empresa=EMPRESA, tem_pdv=TEM_PDV)
    if hasattr(st, "iframe"):
        st.iframe(html_fin, height=1000)
    else:
        components.html(html_fin, height=1000, scrolling=True)
    st.stop()


if st.session_state["pagina"] == "Financeiro":
    pagina_financeiro()

hoje = date.today()
c1, c1b, c1c, c2, c3, c4 = cabecalho([1.1, 1.1, 2.4, 1.1, 1.4, 2.4])
snap = None
if FONTE == "snapshot":
    try:
        with st.spinner("Carregando dados…"):
            snap = snapshot(cfg["url"], cfg["chave"])
            EMPRESA = snap.get("empresa") or EMPRESA
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

if "de" not in st.session_state:
    st.session_state.update(de=_br(padrao[0]), ate=_br(padrao[1]))
with c1:
    st.text_input("De", key="de", placeholder="DD/MM/AAAA", max_chars=10, on_change=_normalizar, args=("de",))
with c1b:
    st.text_input("Até", key="ate", placeholder="DD/MM/AAAA", max_chars=10, on_change=_normalizar, args=("ate",))
components.html(MASCARA_DATA, height=0)
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
        for f in (snapshot, vendas, estoque, snapshot_financeiro):
            f.clear()
        st.rerun()
p_ini, p_fim = periodo_anterior(inicio, fim)

if snap is not None:
    rows = [r for r in snap["rows"] if inicio <= r["d"] <= fim]
    rows_prev = [r for r in snap["rows"] if p_ini <= r["d"] <= p_fim] if p_ini >= snap["inicio"] else []
    est = snap.get("estoque") if fim == snap["fim"] else None
    atualizado, fonte_painel = snap["gerado_em"], "omie"
    hist, hist_ini, hist_fim = snap["rows"], snap["inicio"], snap["fim"]
    if not TEM_PDV:
        rows = [r for r in rows if r.get("ch") != "PDV"]
        rows_prev = [r for r in rows_prev if r.get("ch") != "PDV"]
        hist = [r for r in hist if r.get("ch") != "PDV"]
else:
    try:
        with st.spinner("Consultando a Omie (a primeira carga pode levar alguns minutos)…"):
            rows, ts = (vendas if fim >= hoje.isoformat() else vendas_fechado)(inicio, fim, FONTE)
            rows_prev, _ = vendas_fechado(p_ini, p_fim, FONTE)
            est = estoque(FONTE) if fim >= hoje.isoformat() else None
    except omie.OmieBloqueada:
        st.warning("A Omie bloqueou temporariamente as consultas por excesso de chamadas. Tente de novo em alguns minutos.")
        st.stop()
    except Exception:
        st.error("Não foi possível consultar a fonte de dados.")
        st.stop()
    atualizado = time.strftime("%d/%m/%Y %H:%M", time.localtime(ts))
    fonte_painel = FONTE
    hist, hist_ini, hist_fim = rows_prev + rows, (p_ini if rows_prev else inicio), fim

extra = {"tem_pdv": TEM_PDV, "hist": hist, "hist_inicio": hist_ini, "hist_fim": hist_fim}
html_app = painel.montar_html(rows, rows_prev, inicio, fim, p_ini, p_fim, EMPRESA, atualizado, fonte_painel, est,
                              modo="app", **extra)
html_rel = painel.montar_html(rows, rows_prev, inicio, fim, p_ini, p_fim, EMPRESA, atualizado, fonte_painel, est,
                              **extra)
with c3:
    st.download_button("Baixar relatório (HTML)", html_rel, use_container_width=True,
                       file_name=f"Relatorio_Vendas_{EMPRESA.replace(' ', '_')}_{inicio}_a_{fim}.html", mime="text/html")
with c4:
    comp = f" · comparativo {relatorio.dbr(p_ini)} a {relatorio.dbr(p_fim)}" if rows_prev else ""
    st.caption(f"Atualizado em {atualizado}{comp}")

if hasattr(st, "iframe"):
    st.iframe(html_app, height=1000)
else:
    components.html(html_app, height=1000, scrolling=True)
