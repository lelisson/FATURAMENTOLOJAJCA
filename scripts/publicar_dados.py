"""Publica os dados do painel, criptografados, no branch `dados` do GitHub (lido pelo app Streamlit).

O branch recebe apenas `painel.enc` (JSON compactado e cifrado com Fernet/PAINEL_DATA_KEY) e é
sobrescrito a cada execução, sem acumular histórico.

Uso: python scripts/publicar_dados.py
Roda no GitHub Actions (.github/workflows/publicar.yml, chaves em GitHub Secrets) ou num PC com .env.
"""
import gzip
import json
import os
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from cryptography.fernet import Fernet  # noqa: E402

from backend.app import omie  # noqa: E402

NO_ACTIONS = os.getenv("GITHUB_ACTIONS") == "true"
if NO_ACTIONS:
    BASE = Path(os.environ["RUNNER_TEMP"]) / "painel-omie"
    REMOTO = (f"https://x-access-token:{os.environ['GITHUB_TOKEN']}@github.com/"
              f"{os.environ['GITHUB_REPOSITORY']}.git")
else:
    # Fora do AppData: o Python da Microsoft Store redireciona gravações ali e o git não enxerga a pasta.
    BASE = Path.home() / ".painel-omie"
    REMOTO = os.getenv("PAINEL_DATA_REMOTE", "https://github.com/lelisson/FATURAMENTOLOJAJCA.git")
PASTA = BASE / "dados-repo"
LOG = BASE / "publicar.log"
SEM_JANELA = 0x08000000 if os.name == "nt" else 0


def log(msg: str) -> None:
    if NO_ACTIONS:
        print(msg)
        return
    BASE.mkdir(parents=True, exist_ok=True)
    if LOG.exists() and LOG.stat().st_size > 200_000:
        LOG.write_text("", encoding="utf-8")
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%d/%m/%Y %H:%M:%S')}  {msg}\n")


def inicio_padrao(hoje: date) -> date:
    v = os.getenv("DEFAULT_INICIO", "trimestre").strip().lower()
    if v == "mes":
        return hoje.replace(day=1)
    if v == "trimestre":
        return date(hoje.year, 3 * ((hoje.month - 1) // 3) + 1, 1)
    return date.fromisoformat(v)


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=PASTA, capture_output=True, text=True, creationflags=SEM_JANELA)


def publicar(blob: bytes, carimbo: str) -> None:
    PASTA.mkdir(parents=True, exist_ok=True)
    if not (PASTA / ".git").exists():
        git("init", "-q", "-b", "dados")
        git("remote", "add", "origin", REMOTO)
        if NO_ACTIONS:
            git("config", "user.name", "github-actions[bot]")
            git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    (PASTA / "painel.enc").write_bytes(blob)
    (PASTA / "README.md").write_text("Dados do painel, criptografados e atualizados automaticamente. Não editar.\n",
                                     encoding="utf-8")
    git("add", "-A")
    tem_commit = git("rev-parse", "--verify", "HEAD").returncode == 0
    git("commit", "-q", *(["--amend"] if tem_commit else []), "-m", f"dados {carimbo}")
    r = git("push", "-q", "-f", "origin", "dados")
    if r.returncode != 0:
        raise RuntimeError("git push falhou: " + (r.stderr or "").replace(REMOTO, "<remoto>").strip()[-300:])


def main() -> int:
    chave = os.getenv("PAINEL_DATA_KEY")
    if not chave:
        log("PAINEL_DATA_KEY ausente no .env")
        return 1
    hoje = date.today()
    ini_padrao = ini = inicio_padrao(hoje)
    t0 = time.time()
    try:
        rows = omie.vendas(ini.isoformat(), hoje.isoformat())
    except omie.OmieBloqueada:
        log("Omie bloqueou temporariamente; tenta de novo na próxima execução")
        return 0
    except Exception as e:  # mensagens da Omie não contêm as chaves; mesmo assim só o tipo vai para o log
        log(f"falha ao consultar a Omie: {type(e).__name__}")
        return 1
    try:
        est = omie.estoque_atual()
    except Exception:
        est = None
    carimbo = time.strftime("%d/%m/%Y %H:%M")
    dados = {
        "gerado_em": carimbo, "empresa": os.getenv("OMIE_EMPRESA", "JCA Filial"),
        "inicio": ini.isoformat(), "fim": hoje.isoformat(), "inicio_padrao": ini_padrao.isoformat(),
        "rows": rows, "estoque": est,
    }
    bruto = json.dumps(dados, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    blob = Fernet(chave.encode()).encrypt(gzip.compress(bruto))
    try:
        publicar(blob, carimbo)
    except Exception as e:
        log(f"falha ao publicar: {e}")
        return 1
    log(f"ok: {len(rows)} itens de {ini:%d/%m/%Y} a {hoje:%d/%m/%Y}, {len(blob) // 1024} KB, {time.time() - t0:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
