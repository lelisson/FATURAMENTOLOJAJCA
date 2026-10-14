"""Gera backend/data/vendas_demo.json com vendas FICTÍCIAS (clientes, produtos e valores inventados).

Uso: python scripts/gerar_demo.py
"""
import json
import random
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.transform import linha  # noqa: E402

random.seed(42)
PRODUTOS = [
    ("FILME STRETCH 500X0,025", 180), ("FILME STRETCH 450X0,020", 150), ("PLASTICO BOLHA 120X100", 260),
    ("FILME CONTRATIL 0480X0,070", 420), ("FITA DE ARQUEAR 13MM", 210), ("FITA DE ARQUEAR 16MM", 260),
    ("LONA PRETA 6X100X25", 380), ("LONA CORTADA 6X11", 140), ("FITA ADESIVA TRANSPARENTE 45X100", 9),
    ("SELO PET 13MM", 95), ("ESTICADOR PARA FITA PET", 330), ("PVC FOLHA DUPLA 1,40M", 520),
]
EMPRESAS = [f"EMPRESA EXEMPLO {i:02d} LTDA" for i in range(1, 41)]
CONSUMIDORES = [f"CLIENTE EXEMPLO {i:02d}" for i in range(1, 16)]


def main():
    rows, nf = [], 1000
    d = date(2026, 7, 1)
    while d <= date(2026, 9, 30):
        if d.weekday() < 6:
            for _ in range(random.randint(2, 9)):
                nf += 1
                tipo = random.choices(["pdv", "cf", "emp"], [0.55, 0.1, 0.35])[0]
                cliente = "" if tipo == "pdv" else random.choice(CONSUMIDORES if tipo == "cf" else EMPRESAS)
                for p, preco in random.sample(PRODUTOS, random.choices([1, 2, 3], [0.8, 0.15, 0.05])[0]):
                    qtd = random.randint(1, 6 if tipo == "pdv" else 20)
                    rows.append(linha(d.isoformat(), nf, "Ven" if tipo == "pdv" else "Ped", cliente, p,
                                      round(preco * qtd * random.uniform(0.9, 1.1), 2), tipo == "pdv", tipo == "cf"))
        d += timedelta(days=1)
    out = ROOT / "backend/data/vendas_demo.json"
    out.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    print(f"{len(rows)} itens fictícios em {out}")


if __name__ == "__main__":
    main()
