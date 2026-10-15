"""Valida OMIE_FILIAL_APP_KEY / OMIE_FILIAL_APP_SECRET das variáveis de ambiente (não imprime as chaves).

Uso (na raiz painel-omie/painel-omie):  python scripts/test_conexao.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from app import omie  # noqa: E402

if __name__ == "__main__":
    print(omie.testar_conexao())
