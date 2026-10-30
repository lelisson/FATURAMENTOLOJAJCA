"""Cadastra as chaves em GitHub > Settings > Secrets > Actions sem exibi-las.

Lê as variáveis de ambiente do usuário do Windows (OMIE_FILIAL_* e PAINEL_DATA_KEY).
Requer `gh auth login`. Uso: python scripts/enviar_secrets_github.py
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app import ambiente  # noqa: E402

REPO = "lelisson/FATURAMENTOLOJAJCA"
# secret no GitHub → variável de ambiente no PC
ORIGEM = {
    "OMIE_APP_KEY": "OMIE_FILIAL_APP_KEY",
    "OMIE_APP_SECRET": "OMIE_FILIAL_APP_SECRET",
    "PAINEL_DATA_KEY": "PAINEL_DATA_KEY",
}

falhas = 0
for secret, var in ORIGEM.items():
    valor = ambiente.ler(var)
    if not valor:
        print(f"{secret}: variável {var} ausente")
        falhas += 1
        continue
    r = subprocess.run(["gh", "secret", "set", secret, "-R", REPO], input=valor, text=True, capture_output=True)
    print(f"{secret}: {'ok' if r.returncode == 0 else 'falhou'}")
    falhas += r.returncode != 0
sys.exit(1 if falhas else 0)
