# -*- coding: utf-8 -*-
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
PLANILHA_PADRAO = DATA_DIR / "CUSTOS OLARIA.xlsx"
# No app unificado, a raiz do projeto é o repositório da Filial (um nível acima de olaria/).
ROOT_PROJETO = BASE_DIR.parent
ENV_OMIE = ROOT_PROJETO / ".env"

# Omie → planilha (somente leitura na API). Despesas: Excel manual por enquanto.
OMIE_SYNC_HABILITADO = True
OMIE_LINHA_FATURAMENTO = "Venda de mercadoria (NF-e)"

GALPAO_NOME = "OLARIA"
TITULO_PAINEL = "Painel Controle de Despesas - Galpão Olaria"
# Teto de referência por mês (KPIs e limite disponível no painel)
TETO_GASTOS_MENSAL = 50_000.0
TITULO_DASHBOARD = TITULO_PAINEL
# Painel Streamlit: só leitura; lançamentos no Excel em PLANILHA_PADRAO
PAINEL_SOMENTE_LEITURA = True

MESES = [
    "Jan",
    "Fev",
    "Mar",
    "Abr",
    "Mai",
    "Jun",
    "Jul",
    "Ago",
    "Set",
    "Out",
    "Nov",
    "Dez",
]

CATEGORIAS_PADRAO = [
    "Pessoal",
    "Utilidades",
    "Seguros e Segurança",
    "Manutenção",
    "Impostos e Taxas",
    "Veiculo",
    "Insumo",
    "Abastecimento",
    "Outros",
]

# Linhas fixas na aba Lançamentos (1-based, como no Excel)
LANC_HEADER_ROW = 4
LANC_FIRST_DATA_ROW = 5
LANC_COL_DESPESA = 1
LANC_COL_CATEGORIA = 2
LANC_COL_FIRST_MES = 3  # Jan
LANC_COL_TOTAL = 15

FAT_HEADER_ROW = 4
FAT_FIRST_DATA_ROW = 5
FAT_TOTAL_ROW = 16

CAD_HEADER_ROW = 4
CAD_FIRST_DATA_ROW = 5
