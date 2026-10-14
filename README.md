# Painel de Vendas · JCA Filial + Omie

Painel igual ao relatório estático do trimestre, mas alimentado pela API Omie (NF de saída).  
As **chaves da API ficam somente no `.env` desta pasta**, no PC onde o painel roda — **não vão para git, nuvem nem frontend**.

## Estrutura

```
painel-omie/
  .env                 ← você cria (copie de .env.example)
  Iniciar Painel.bat   ← atalho no Windows
  backend/app/         ← FastAPI + cliente Omie
  frontend/index.html  ← painel (Chart.js)
  scripts/             ← teste de conexão e inspeção de NF
```

## 1. Rodar com dados de exemplo (sem chaves)

```powershell
cd "...\painel-omie\painel-omie"
python -m venv .venv
.\.venv\Scripts\activate
pip install -r backend\requirements.txt
copy .env.example .env
uvicorn app.main:app --app-dir backend --reload
```

Abra http://localhost:8000

## 2. Conectar vendas reais da JCA Filial (Omie)

1. No Omie da filial: crie/obtenha **App Key** e **App Secret** (somente leitura basta para consultas).
2. Edite o `.env`:
   - `OMIE_APP_KEY` e `OMIE_APP_SECRET`
   - `DATA_SOURCE=omie`
   - Ajuste `DEFAULT_INICIO` / `DEFAULT_FIM` se quiser outro período.
3. Teste: `python scripts/test_conexao.py`
4. (Opcional) Ver JSON bruto de NF: `python scripts/inspect_omie.py 2026-10-01 2026-10-07`
5. Inicie: duplo clique em **Iniciar Painel.bat** ou o comando uvicorn acima.

O navegador **atualiza sozinho** a cada `PANEL_REFRESH_SEC` segundos (padrão 300). O servidor também cacheia a API por `CACHE_TTL` segundos.

Período na URL: `http://localhost:8000/?inicio=2026-07-01&fim=2026-09-30`

## Oportunidades (só com DATA_SOURCE=omie)

Compara o período na tela com o **trimestre anterior inteiro** e com o **estoque de hoje**:

- **Clientes que pararam de comprar**: compraram no trimestre anterior e ainda não compraram no período atual.
- **Produtos que pararam de vender ou caíram**: zeraram ou estão abaixo de metade do ritmo diário anterior.
- **Produtos com estoque e sem venda**: saldo hoje (`ListarPosEstoque`) sem venda no período, com custo parado.

No começo de um trimestre as listas de "parados" são naturalmente longas; elas diminuem conforme as vendas entram.

## Relatório para a diretoria (HTML estático)

Botão **Gerar relatório** no painel: escolha o modelo, o mês (ou um período personalizado) e clique em **Visualizar** ou **Baixar HTML**.
Também por URL: `http://localhost:8000/api/relatorio?inicio=2026-09-01&fim=2026-09-30` (acrescente `&download=true` para baixar e `&modelo=executivo` para o documento A4).

- **Layout do painel** (padrão): o próprio `frontend/index.html` com os dados do período e o Chart.js (`frontend/vendor/`) embutidos. Filtros, abas e tema funcionam offline; botão Imprimir / PDF.
- **Documento executivo**: página A4 com destaques em texto e gráficos SVG.
- Arquivo único, sem dependências externas: abre offline e imprime em PDF.
- Compara com o mês anterior (mesmo intervalo de dias se o mês estiver em andamento) ou com o período de mesma duração imediatamente anterior.
- Uma cópia fica em `relatorios/` (fora do git). Nenhuma chave vai para o arquivo.

## Streamlit (deploy)

`streamlit_app.py` mostra o mesmo painel (`frontend/index.html` com os dados embutidos), com seletor de período e botão para baixar o relatório HTML.

- Local: `streamlit run streamlit_app.py` (usa o `.env`).
- Streamlit Community Cloud: arquivo principal `streamlit_app.py`; configuração em **Settings > Secrets** no formato de `.streamlit/secrets.toml.example`. `APP_PASSWORD` (opcional) pede senha para abrir.
- **Modo recomendado (só visualização):** o PC roda `scripts/publicar_dados.py` a cada 30 min (tarefa agendada "PainelOmie - Publicar dados"). Ele consulta a Omie com as chaves locais, criptografa os dados (Fernet, `PAINEL_DATA_KEY`) e sobrescreve `painel.enc` no branch `dados`. O Streamlit recebe só `PAINEL_DATA_URL` e `PAINEL_DATA_KEY`; as chaves da Omie nunca saem do PC. Log em `%USERPROFILE%\.painel-omie\publicar.log`.
- Sem credenciais, o app abre com `backend/data/vendas_demo.json` (dados fictícios, gerados por `scripts/gerar_demo.py`).
- Teste rápido: `python scripts/testar_streamlit.py`.

## Segurança

- `.env` está no `.gitignore` — nunca faça commit das chaves.
- O frontend só chama `/api/vendas` no mesmo servidor; **app_key/app_secret não saem do backend**.
- Para expor na rede, coloque autenticação na frente (dados financeiros).

## Conferência

Compare o **faturamento total** do painel com o relatório de faturamento do Omie no mesmo período.  
Se canal (PDV / consumo final / empresas) divergir da planilha Omie, rode `inspect_omie.py` e ajuste `mapear_nf` em `backend/app/omie.py` (campos `pedido.consumidor_final`, operação 13 = PDV, modelo 65 = NFC-e).

## Limitações

- Textos de “Sugestões” e “Resumo executivo” são do 3º tri de exemplo; com `DATA_SOURCE=omie` essas seções ficam ocultas e entra a seção “Oportunidades”.
- A Omie bloqueia por alguns minutos um método chamado em excesso. O painel respeita o bloqueio e guarda em `backend/data/cache_pedidos.json` o indicador de consumo final de cada pedido, para não consultar o mesmo pedido de novo.
- A API Omie não traz quantidade física por item neste fluxo; rankings usam faturamento e nº de linhas em NF.
