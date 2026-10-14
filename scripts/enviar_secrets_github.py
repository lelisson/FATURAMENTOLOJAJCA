"""Cadastra as chaves do .env em GitHub > Settings > Secrets > Actions sem exibi-las.

Requer `gh auth login`. Uso: python scripts/enviar_secrets_github.py
"""
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
REPO = "lelisson/FATURAMENTOLOJAJCA"
NOMES = ("OMIE_APP_KEY", "OMIE_APP_SECRET", "PAINEL_DATA_KEY")

env = dotenv_values(ROOT / ".env")
falhas = 0
for nome in NOMES:
    valor = (env.get(nome) or "").strip()
    if not valor:
        print(f"{nome}: ausente no .env")
        falhas += 1
        continue
    r = subprocess.run(["gh", "secret", "set", nome, "-R", REPO], input=valor, text=True, capture_output=True)
    print(f"{nome}: {'ok' if r.returncode == 0 else 'falhou'}")
    falhas += r.returncode != 0
sys.exit(1 if falhas else 0)
