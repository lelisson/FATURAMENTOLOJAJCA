"""Levantamento (somente leitura) de devoluções e transferências nas NF-e da Omie.

Uso: python scripts/levantar_devolucoes.py 2026-07-01 2026-10-14 [--matriz]
Grava a amostra bruta em backend/data/raw_devolucoes[_matriz].json (fora do git).
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
from backend.app import omie  # noqa: E402


def listar(inicio, fim, tp):
    return omie._paginar(
        "ListarNF", omie.EP_NF,
        lambda p: {"pagina": p, "registros_por_pagina": omie.POR_PAGINA_NF, "apenas_importado_api": "N",
                   "cDetalhesPedido": "S", "dEmiInicial": omie._br(inicio), "dEmiFinal": omie._br(fim), "tpNF": tp},
        "nfCadastro", "total_de_paginas")


def main():
    inicio, fim = sys.argv[1], sys.argv[2]
    matriz = "--matriz" in sys.argv
    if matriz:
        omie.carregar_chaves_matriz_local()
        omie.usar_empresa("matriz")
    amostra = {}
    for tp, nome in (("0", "ENTRADA"), ("1", "SAIDA")):
        nfs = listar(inicio, fim, tp)
        emit = {(nf.get("nfEmitInt") or {}).get("cRazao") or (nf.get("nfEmitInt") or {}).get("cNome") for nf in nfs[:20]}
        pedidos = {int((nf.get("compl") or {}).get("nIdPedido") or 0) for nf in nfs} - {0}
        print(f"\n{nome}: emitentes (amostra) {sorted(e for e in emit if e)[:3]} | pedidos distintos: {len(pedidos)}")
        grupos = defaultdict(lambda: {"nfs": set(), "valor": 0.0})
        for nf in nfs:
            if omie._cancelada_nf(nf):
                continue
            ide = nf.get("ide") or {}
            fin = ide.get("finNFe")
            op = omie._codigo_operacao(nf)
            for det in nf.get("det") or []:
                pr = det.get("prod") or {}
                cfop = str(pr.get("CFOP") or pr.get("cCFOP") or "?")
                g = grupos[(cfop, str(fin), op)]
                g["nfs"].add(ide.get("nNF"))
                g["valor"] += omie._f(pr.get("vProd")) - omie._f(pr.get("vDesc"))
                amostra.setdefault(f"{nome}-{cfop}", nf)
        print(f"\n== NF de {nome} ({len(nfs)} notas) — CFOP | finNFe | operação | qtde NF | valor")
        for (cfop, fin, op), g in sorted(grupos.items()):
            print(f"  {cfop:>5} | {fin:>4} | {op:>4} | {len(g['nfs']):>4} | {g['valor']:>12,.2f}")
    cupons = omie.listar_cupons_bruto(inicio, fim)
    print(f"\nCupons fiscais (PDV): {len(cupons)}")
    destino = ROOT / f"backend/data/raw_devolucoes{'_matriz' if matriz else ''}.json"
    destino.write_text(json.dumps(amostra, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
