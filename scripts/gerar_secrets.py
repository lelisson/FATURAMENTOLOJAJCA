"""Gera .streamlit/secrets.toml (fora do git) com o que colar em Settings > Secrets do Streamlit Cloud.

Não inclui as chaves da Omie nem a senha: só o hash dela (PBKDF2-SHA256).
Uso: python scripts/gerar_secrets.py              (mantém a senha atual)
     python scripts/gerar_secrets.py --nova-senha (gera outra e grava em ~/.painel-omie/senha-streamlit.txt)
"""
import hashlib
import secrets
import sys
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
env = dotenv_values(ROOT / ".env")
destino = ROOT / ".streamlit" / "secrets.toml"
arquivo_senha = Path.home() / ".painel-omie" / "senha-streamlit.txt"
ITERACOES = 600_000


def gerar_hash(senha: str) -> str:
    sal = secrets.token_bytes(16)
    h = hashlib.pbkdf2_hmac("sha256", senha.encode(), sal, ITERACOES).hex()
    return f"pbkdf2_sha256${ITERACOES}${sal.hex()}${h}"


hash_atual = ""
if destino.exists():
    for linha in destino.read_text(encoding="utf-8").splitlines():
        if linha.startswith("APP_PASSWORD_HASH"):
            hash_atual = linha.split("=", 1)[1].strip().strip('"')

if "--nova-senha" in sys.argv or not hash_atual:
    senha = "JCA-" + secrets.token_urlsafe(9)
    hash_atual = gerar_hash(senha)
    arquivo_senha.parent.mkdir(parents=True, exist_ok=True)
    arquivo_senha.write_text(
        f"Senha do painel no Streamlit: {senha}\n\n"
        "Guarde em local seguro e apague este arquivo. Ela não fica salva em nenhum outro lugar.\n",
        encoding="utf-8",
    )
    print(f"Nova senha gravada em: {arquivo_senha}")

linhas = [
    f'PAINEL_DATA_URL = "{env["PAINEL_DATA_URL"].strip()}"',
    f'PAINEL_DATA_KEY = "{env["PAINEL_DATA_KEY"].strip()}"',
    f'APP_PASSWORD_HASH = "{hash_atual}"',
    f'OMIE_EMPRESA = "{(env.get("OMIE_EMPRESA") or "JCA Filial").strip()}"',
]
destino.write_text("\n".join(linhas) + "\n", encoding="utf-8")
print(f"Gerado: {destino}")
