# Prompt para colar no Cursor

Este projeto é um painel de vendas (frontend/index.html, Chart.js) servido por um backend
FastAPI (backend/app). O painel consome GET /api/vendas, que devolve
{inicio, fim, fonte, rows:[{d, nf, v, c, ch, f, p, x}]}:
d=data AAAA-MM-DD, nf=nº da NF, v=id da venda, c=cliente, ch=canal
("PDV" | "Pedido – consumo final" | "Pedido – empresas"), f=família do produto, p=produto, x=valor líquido do item.

Tarefa: implementar `mapear_nf` em backend/app/omie.py para a API REAL do Omie.
1. Leia a documentação oficial do Omie (developer.omie.com.br) e confirme endpoint, método,
   filtros de período e paginação de notas fiscais de venda. Ajuste ENDPOINT, CALL e os filtros.
2. Rode `python scripts/inspect_omie.py 2026-07-01 2026-07-07`, leia backend/data/raw_amostra.json
   e implemente `mapear_nf` usando `transform.linha(...)`, uma linha por item da nota.
3. Regras: ignorar notas não autorizadas/canceladas; valor = total do item líquido de desconto;
   PDV = NFC-e / venda de balcão; consumo final conforme o indicador da nota; cliente sem
   identificação = vazio (o transform converte para "Cliente Consumidor / Sem Tomador").
4. Valide: com DATA_SOURCE=omie, o total do período deve bater com o relatório de faturamento do Omie.
5. Nunca logar nem retornar OMIE_APP_KEY/OMIE_APP_SECRET. Não colocar chaves no frontend.
