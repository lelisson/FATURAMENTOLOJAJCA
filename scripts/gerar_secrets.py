"""Gera .streamlit/secrets.toml (fora do git) com o que colar em Settings > Secrets do Streamlit Cloud.

Não inclui as chaves da Omie. Uso: python scripts/gerar_secrets.py
"""
import secrets
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
env = dotenv_values(ROOT / ".env")
destino = ROOT / ".streamlit" / "secrets.toml"

senha = "JCA-" + secrets.token_urlsafe(6)
if destino.exists():
    for linha in destino.read_text(encoding="utf-8").splitlines():
        if linha.startswith("APP_PASSWORD"):
            senha = linha.split("=", 1)[1].strip().strip('"') or senha

linhas = [
    f'PAINEL_DATA_URL = "{env["PAINEL_DATA_URL"].strip()}"',
    f'PAINEL_DATA_KEY = "{env["PAINEL_DATA_KEY"].strip()}"',
    f'APP_PASSWORD = "{senha}"',
    f'OMIE_EMPRESA = "{(env.get("OMIE_EMPRESA") or "JCA Filial").strip()}"',
]
destino.write_text("\n".join(linhas) + "\n", encoding="utf-8")
print(f"Gerado: {destino}")
