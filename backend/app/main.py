import json
import os
import threading
import time
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

from . import omie, painel, relatorio  # noqa: E402  (depois do load_dotenv)

app = FastAPI(title="Painel de Vendas")
_cache: dict = {}
_atualizando: set = set()
_lock = threading.Lock()


def periodo_padrao() -> tuple[str, str]:
    """DEFAULT_INICIO/DEFAULT_FIM aceitam datas AAAA-MM-DD ou 'trimestre' / 'mes' (período atual até hoje)."""
    ini = os.getenv("DEFAULT_INICIO", "trimestre").strip().lower()
    fim = os.getenv("DEFAULT_FIM", "hoje").strip().lower()
    hoje = date.today()
    if ini == "trimestre":
        ini = date(hoje.year, 3 * ((hoje.month - 1) // 3) + 1, 1).isoformat()
    elif ini == "mes":
        ini = date(hoje.year, hoje.month, 1).isoformat()
    if fim == "hoje":
        fim = hoje.isoformat()
    return ini, fim


def _buscar(fonte: str, inicio: str, fim: str) -> list[dict]:
    if fonte == "omie":
        return omie.vendas(inicio, fim)
    amostra = ROOT / "backend/data/vendas_sample.json"
    if not amostra.exists():
        amostra = ROOT / "backend/data/vendas_demo.json"
    rows = json.loads(amostra.read_text(encoding="utf-8"))
    return [r for r in rows if inicio <= r["d"] <= fim]


def _atualizar_em_segundo_plano(chave: tuple) -> None:
    with _lock:
        if chave in _atualizando:
            return
        _atualizando.add(chave)

    def run():
        try:
            _cache[chave] = (time.time(), _buscar(*chave))
        except Exception:
            pass
        finally:
            with _lock:
                _atualizando.discard(chave)

    threading.Thread(target=run, daemon=True).start()


def carregar(inicio: str, fim: str):
    """Devolve o cache na hora; se vencido, atualiza em segundo plano (a Omie leva minutos)."""
    fonte = os.getenv("DATA_SOURCE", "sample")
    ttl = int(os.getenv("CACHE_TTL", "300"))
    if fim < date.today().isoformat():
        ttl = max(ttl, 6 * 3600)  # período fechado quase não muda
    chave = (fonte, inicio, fim)
    hit = _cache.get(chave)
    if hit:
        if time.time() - hit[0] >= ttl:
            _atualizar_em_segundo_plano(chave)
        return hit[1], fonte, hit[0]
    while chave in _atualizando:
        time.sleep(1)
    if chave in _cache:
        return _cache[chave][1], fonte, _cache[chave][0]
    rows = _buscar(fonte, inicio, fim)
    _cache[chave] = (time.time(), rows)
    return rows, fonte, _cache[chave][0]


def trimestre_anterior(inicio: str) -> tuple[str, str]:
    d = date.fromisoformat(inicio)
    q = 3 * ((d.month - 1) // 3) + 1
    ano, mes = (d.year, q - 3) if q > 3 else (d.year - 1, 10)
    fim = date(ano + (mes + 3 > 12), (mes + 2) % 12 + 1, 1) - timedelta(days=1)
    return date(ano, mes, 1).isoformat(), fim.isoformat()


@app.on_event("startup")
def aquecer_cache():
    fonte = os.getenv("DATA_SOURCE", "sample")
    ini, fim = periodo_padrao()

    _atualizar_em_segundo_plano((fonte, ini, fim))


_estoque: dict = {}


@app.get("/api/estoque")
def estoque():
    if os.getenv("DATA_SOURCE", "sample") != "omie":
        return {"fonte": "sample", "itens": []}
    hit = _estoque.get("dados")
    if not hit or time.time() - hit[0] > 3600:
        try:
            _estoque["dados"] = (time.time(), omie.estoque_atual())
        except Exception:
            if not hit:
                raise HTTPException(502, "Falha ao consultar o estoque na Omie.")
    ts, itens = _estoque["dados"]
    return {"fonte": "omie", "atualizado_em": time.strftime("%d/%m/%Y %H:%M", time.localtime(ts)), "itens": itens}


@app.get("/api/periodo-anterior")
def periodo_anterior(inicio: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$")):
    ini, fim = trimestre_anterior(inicio)
    return {"inicio": ini, "fim": fim}


@app.get("/api/health")
def health():
    return {"ok": True, "fonte": os.getenv("DATA_SOURCE", "sample")}


@app.get("/api/config")
def config():
    ini, fim = periodo_padrao()
    return {
        "empresa": os.getenv("OMIE_EMPRESA", "JCA Filial"),
        "fonte": os.getenv("DATA_SOURCE", "sample"),
        "inicio_padrao": ini,
        "fim_padrao": fim,
        "cache_ttl": int(os.getenv("CACHE_TTL", "300")),
        "refresh_sec": int(os.getenv("PANEL_REFRESH_SEC", "300")),
    }


@app.get("/api/vendas")
def vendas(inicio: str = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
           fim: str = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$")):
    ini_p, fim_p = periodo_padrao()
    inicio = inicio or ini_p
    fim = fim or fim_p
    try:
        rows, fonte, ts = carregar(inicio, fim)
    except omie.OmieBloqueada:
        raise HTTPException(503, "A Omie bloqueou temporariamente as consultas. O painel tenta de novo sozinho.")
    except RuntimeError as e:
        msg = str(e)
        if "APP_KEY" in msg or "Credenciais" in msg:
            raise HTTPException(503, "Credenciais Omie não configuradas nas variáveis de ambiente deste PC.")
        raise HTTPException(502, "Falha ao consultar o Omie.")
    except Exception:  # nunca devolva app_key/app_secret em mensagens de erro
        raise HTTPException(502, "Falha ao consultar a fonte de dados.")
    return {
        "inicio": inicio,
        "fim": fim,
        "fonte": fonte,
        "atualizado_em": time.strftime("%d/%m/%Y %H:%M", time.localtime(ts)),
        "rows": rows,
    }


def linhas_periodo(inicio: str, fim: str):
    """Recorta de um período já em cache que cubra o intervalo; só consulta a Omie se nenhum cobrir."""
    fonte = os.getenv("DATA_SOURCE", "sample")
    cobre = lambda k: k[0] == fonte and k[1] <= inicio and k[2] >= fim
    while any(cobre(k) and k not in _cache for k in list(_atualizando)):
        time.sleep(1)
    for (f, ini_c, fim_c), (ts, rows) in sorted(list(_cache.items()), key=lambda kv: -kv[1][0]):
        if f == fonte and ini_c <= inicio and fim_c >= fim:
            return [r for r in rows if inicio <= r["d"] <= fim], ts
    rows, _, ts = carregar(inicio, fim)
    return rows, ts


def _painel_estatico(rows, rows_prev, inicio, fim, p_ini, p_fim, empresa, atualizado) -> str:
    """O próprio painel (frontend/index.html) com dados e Chart.js embutidos: abre offline, sem API."""
    fonte = os.getenv("DATA_SOURCE", "sample")
    estoque_itens = None
    if fonte == "omie" and fim >= date.today().isoformat():
        try:
            estoque_itens = estoque()["itens"]
        except Exception:
            pass
    return painel.montar_html(rows, rows_prev, inicio, fim, p_ini, p_fim, empresa, atualizado, fonte, estoque_itens)


@app.get("/api/relatorio")
def relatorio_html(inicio: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
                   fim: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
                   download: bool = False,
                   modelo: str = Query("painel", pattern="^(painel|executivo)$")):
    if inicio > fim:
        raise HTTPException(400, "Período inválido.")
    fim = min(fim, date.today().isoformat())
    p_ini, p_fim = relatorio.periodo_comparacao(inicio, fim)
    try:
        rows, ts = linhas_periodo(inicio, fim)
        rows_prev, _ = linhas_periodo(p_ini, p_fim)
    except omie.OmieBloqueada:
        raise HTTPException(503, "A Omie bloqueou temporariamente as consultas. Tente de novo em alguns minutos.")
    except Exception:
        raise HTTPException(502, "Falha ao consultar a fonte de dados.")
    empresa = os.getenv("OMIE_EMPRESA", "JCA Filial")
    atualizado = time.strftime("%d/%m/%Y %H:%M", time.localtime(ts))
    if modelo == "executivo":
        html = relatorio.gerar(rows, rows_prev, inicio, fim, p_ini, p_fim, empresa, atualizado)
    else:
        html = _painel_estatico(rows, rows_prev, inicio, fim, p_ini, p_fim, empresa, atualizado)
    sufixo = "" if modelo == "painel" else "_executivo"
    nome = f"Relatorio_Vendas_{empresa.replace(' ', '_')}_{inicio}_a_{fim}{sufixo}.html"
    pasta = ROOT / "relatorios"
    pasta.mkdir(exist_ok=True)
    (pasta / nome).write_text(html, encoding="utf-8")
    headers = {"Content-Disposition": f'attachment; filename="{nome}"'} if download else {}
    return HTMLResponse(html, headers=headers)


# Serve o painel (mesma origem, sem CORS). Deve ficar por último.
app.mount("/", StaticFiles(directory=ROOT / "frontend", html=True), name="frontend")
