"""Regras de limpeza e classificação. Mesma lógica usada na análise da planilha."""
import re

ANON = "Cliente Consumidor / Sem Tomador"
CANAIS = ("PDV", "Pedido – consumo final", "Pedido – empresas")

_FAMILIAS = [
    ("STRETCH", "Filme Stretch"), ("APLICADOR DE FILME", "Filme Stretch"),
    ("BOLHA", "Plástico Bolha"), ("CONTRATIL", "Filme Contrátil"),
    ("ARQUEAR", "Fita de Arquear"), ("LONA", "Lona"),
    ("FITA ADESIVA", "Fita Adesiva"), ("PHOENIX", "Fita Adesiva"),
    ("SELO", "Selos e Acessórios PET"), ("SELADOR", "Selos e Acessórios PET"),
    ("ESTICADOR", "Selos e Acessórios PET"), ("PVC", "PVC Folha Dupla"),
]


def normaliza_produto(p: str) -> str:
    p = (p or "").upper().replace("CONTRÁTIL", "CONTRATIL").replace('"', "")
    p = re.sub(r"\s+", " ", p.rstrip(";").strip())
    return re.sub(r"(?<=\d)\s*X\s*(?=\d)", "X", p)


def familia(p: str) -> str:
    for k, v in _FAMILIAS:
        if k in p:
            return v
    return "Outros"


def classifica_canal(is_pdv: bool, consumo_final: bool) -> str:
    if is_pdv:
        return "PDV"
    return "Pedido – consumo final" if consumo_final else "Pedido – empresas"


def linha(data_iso: str, nf, serie_ou_origem: str, cliente: str, produto: str,
          valor: float, is_pdv: bool, consumo_final: bool, codigo: str = "") -> dict:
    """Formato único que o painel consome (campos curtos para reduzir o JSON)."""
    nf_int = int(re.sub(r"\D", "", str(nf)) or 0)
    p = normaliza_produto(produto)
    cli = (cliente or "").strip() or ANON
    return {
        "cod": str(codigo or "").strip(),
        "d": data_iso,
        "nf": str(nf_int).zfill(8),
        # venda = origem + NF + dia/mês + cliente (a numeração PDV e pedido se cruza)
        "v": f"{serie_ou_origem}-{nf_int}-{data_iso[5:7]}{data_iso[8:10]}-{cli}",
        "c": cli,
        "ch": classifica_canal(is_pdv, consumo_final),
        "f": familia(p),
        "p": p,
        "x": round(float(valor), 2),
    }
