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

from backend.app import ambiente, omie  # noqa: E402

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


# empresa → (arquivo no branch `dados`, variável com o nome exibido, nome padrão)
EMPRESAS = {
    "filial": ("painel.enc", "OMIE_EMPRESA", "JCA Filial"),
    "matriz": ("painel_matriz.enc", "OMIE_EMPRESA_MATRIZ", "JCA Matriz"),
}


def publicar(blobs: dict[str, bytes], carimbo: str) -> None:
    PASTA.mkdir(parents=True, exist_ok=True)
    if not (PASTA / ".git").exists():
        git("init", "-q", "-b", "dados")
        git("remote", "add", "origin", REMOTO)
        if NO_ACTIONS:
            git("config", "user.name", "github-actions[bot]")
            git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    # Parte do que já está publicado: a empresa que falhar nesta execução mantém o arquivo anterior.
    if git("fetch", "-q", "--depth", "1", "origin", "dados").returncode == 0:
        git("reset", "-q", "--hard", "FETCH_HEAD")
    for arquivo, blob in blobs.items():
        (PASTA / arquivo).write_bytes(blob)
    (PASTA / "README.md").write_text("Dados do painel, criptografados e atualizados automaticamente. Não editar.\n",
                                     encoding="utf-8")
    git("add", "-A")
    tem_commit = git("rev-parse", "--verify", "HEAD").returncode == 0
    git("commit", "-q", *(["--amend"] if tem_commit else []), "-m", f"dados {carimbo}")
    r = git("push", "-q", "-f", "origin", "dados")
    if r.returncode != 0:
        raise RuntimeError("git push falhou: " + (r.stderr or "").replace(REMOTO, "<remoto>").strip()[-300:])


# Meses fechados não são consultados de novo. Mude VERSAO_CONGELADO quando a regra de faturamento mudar.
VERSAO_CONGELADO = 1
# Mês anterior fecha no dia 1 às 23:59 (NF-e pode ser cancelada em até 24 h da autorização).
DIA_FECHAMENTO = int(os.getenv("DIA_FECHAMENTO", "2"))


def mes_fechado_ate(hoje: date) -> str:
    """Meses anteriores ao retornado (AAAA-MM) estão fechados; o anterior fecha no DIA_FECHAMENTO do mês."""
    if hoje.day >= DIA_FECHAMENTO:
        return f"{hoje:%Y-%m}"
    return f"{hoje.year - (hoje.month == 1)}-{(hoje.month - 2) % 12 + 1:02d}"


def arquivo_congelado(empresa: str) -> Path:
    return omie.PASTA_DADOS / f"cache_congelado_{empresa}.enc"


def ler_congelado(empresa: str, fernet: Fernet) -> dict[str, list[dict]]:
    arq = arquivo_congelado(empresa)
    if os.getenv("REPROCESSAR") == "true" or not arq.exists():
        return {}
    try:
        dados = json.loads(gzip.decompress(fernet.decrypt(arq.read_bytes())))
    except Exception:
        return {}
    return dados["meses"] if dados.get("versao") == VERSAO_CONGELADO else {}


def gravar_congelado(empresa: str, fernet: Fernet, meses: dict[str, list[dict]]) -> None:
    bruto = json.dumps({"versao": VERSAO_CONGELADO, "meses": meses}, ensure_ascii=False,
                       separators=(",", ":")).encode("utf-8")
    arq = arquivo_congelado(empresa)
    arq.parent.mkdir(parents=True, exist_ok=True)
    arq.write_bytes(fernet.encrypt(gzip.compress(bruto)))


def gerar(empresa: str, fernet: Fernet, hoje: date) -> bytes | None:
    _, var_nome, nome_padrao = EMPRESAS[empresa]
    omie.usar_empresa(empresa)
    try:
        omie._credenciais()
    except RuntimeError:
        log(f"{empresa}: chaves não configuradas; mantém os dados anteriores")
        return None
    ini_padrao = ini = inicio_padrao(hoje)
    t0 = time.time()
    congelado = ler_congelado(empresa, fernet)
    try:
        rows, congelado_novo = omie.vendas_congelando(ini.isoformat(), hoje.isoformat(), congelado,
                                                      mes_fechado_ate(hoje))
    except omie.OmieBloqueada:
        log(f"{empresa}: Omie bloqueou temporariamente; tenta de novo na próxima execução")
        return None
    except Exception as e:  # mensagens da Omie não contêm as chaves; mesmo assim só o tipo vai para o log
        log(f"{empresa}: falha ao consultar a Omie: {type(e).__name__}")
        return None
    gravar_congelado(empresa, fernet, congelado_novo)
    try:
        est = omie.estoque_atual()
    except Exception:
        est = None
    dados = {
        "gerado_em": time.strftime("%d/%m/%Y %H:%M"), "empresa": os.getenv(var_nome, nome_padrao),
        "inicio": ini.isoformat(), "fim": hoje.isoformat(), "inicio_padrao": ini_padrao.isoformat(),
        "rows": rows, "estoque": est,
    }
    bruto = json.dumps(dados, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    blob = fernet.encrypt(gzip.compress(bruto))
    log(f"{empresa}: {len(rows)} itens de {ini:%d/%m/%Y} a {hoje:%d/%m/%Y}, {len(blob) // 1024} KB, "
        f"{time.time() - t0:.0f}s; meses congelados: {', '.join(sorted(congelado_novo)) or 'nenhum'} "
        f"(reaproveitados: {len(congelado)})")
    return blob


def main() -> int:
    chave = ambiente.ler("PAINEL_DATA_KEY")
    if not chave:
        log("PAINEL_DATA_KEY ausente")
        return 1
    if not NO_ACTIONS:
        omie.carregar_chaves_matriz_local()
    fernet = Fernet(chave.encode())
    hoje = date.today()
    blobs = {}
    for empresa, (arquivo, _, _) in EMPRESAS.items():
        blob = gerar(empresa, fernet, hoje)
        if blob:
            blobs[arquivo] = blob
    if not blobs:
        return 1
    try:
        publicar(blobs, time.strftime("%d/%m/%Y %H:%M"))
    except Exception as e:
        log(f"falha ao publicar: {e}")
        return 1
    log(f"ok: publicado {', '.join(blobs)}")
    return 0 if len(blobs) == len(EMPRESAS) else 1


if __name__ == "__main__":
    sys.exit(main())
