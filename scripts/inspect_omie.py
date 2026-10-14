"""Mostra a resposta bruta do Omie para você ajustar omie.mapear_nf.
Uso (na raiz do projeto):  python scripts/inspect_omie.py 2026-07-01 2026-07-07
Salva em backend/data/raw_amostra.json (ignorado pelo git). Não imprime as chaves."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")
from app import omie

ini, fim = sys.argv[1], sys.argv[2]
amostra = []
for nf in omie.listar_nf_bruto(ini, fim):
    amostra.append(nf)
    if len(amostra) >= 5:
        break
(ROOT / "backend/data/raw_amostra.json").write_text(json.dumps(amostra, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"{len(amostra)} NF salvas em backend/data/raw_amostra.json")
if amostra:
    print("Chaves de nível 1:", list(amostra[0].keys()))
