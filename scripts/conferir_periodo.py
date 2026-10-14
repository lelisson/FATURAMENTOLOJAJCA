"""Resumo do faturamento do período direto da Omie (para conferir com o relatório da Omie).

Uso (na raiz painel-omie/painel-omie):  python scripts/conferir_periodo.py 2026-07-01 2026-09-30
"""
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from app import omie  # noqa: E402

ini, fim = sys.argv[1], sys.argv[2]
t0 = time.time()
rows = omie.vendas(ini, fim)
total = sum(r["x"] for r in rows)
print(f"Período {ini} a {fim}")
print(f"Itens: {len(rows)}  Vendas: {len(set(r['v'] for r in rows))}  Faturamento: R$ {total:,.2f}")
for ch, _ in Counter(r["ch"] for r in rows).most_common():
    sub = [r for r in rows if r["ch"] == ch]
    print(f"  {ch}: R$ {sum(r['x'] for r in sub):,.2f}  ({len(set(r['v'] for r in sub))} vendas)")
print(f"Tempo: {time.time() - t0:.0f}s")
