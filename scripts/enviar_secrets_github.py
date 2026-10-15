"""Cadastra as chaves em GitHub > Settings > Secrets > Actions sem exibi-las.

Filial e PAINEL_DATA_KEY vêm do .env deste projeto; a matriz, do .env do projeto de estoque (pasta acima),
que só é lido. Requer `gh auth login`. Uso: python scripts/enviar_secrets_github.py
"""
import os
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app import omie  # noqa: E402

REPO = "lelisson/FATURAMENTOLOJAJCA"
NOMES = ("OMIE_APP_KEY", "OMIE_APP_SECRET", "PAINEL_DATA_KEY", "OMIE_MATRIZ_APP_KEY", "OMIE_MATRIZ_APP_SECRET")

env = dotenv_values(ROOT / ".env")
omie.carregar_chaves_matriz_local()
falhas = 0
for nome in NOMES:
    valor = (env.get(nome) or os.getenv(nome) or "").strip()
    if not valor:
        print(f"{nome}: ausente")
        falhas += 1
        continue
    r = subprocess.run(["gh", "secret", "set", nome, "-R", REPO], input=valor, text=True, capture_output=True)
    print(f"{nome}: {'ok' if r.returncode == 0 else 'falhou'}")
    falhas += r.returncode != 0
sys.exit(1 if falhas else 0)
