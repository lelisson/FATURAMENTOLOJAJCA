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
2. Crie as variáveis de ambiente **do usuário** do Windows (não no `.env`): `OMIE_FILIAL_APP_KEY`, `OMIE_FILIAL_APP_SECRET` e `PAINEL_DATA_KEY`.
3. Edite o `.env`:
   - `DATA_SOURCE=omie`
   - Ajuste `DEFAULT_INICIO` / `DEFAULT_FIM` se quiser outro período.
4. Teste: `python scripts/test_conexao.py`
5. (Opcional) Ver JSON bruto de NF: `python scripts/inspect_omie.py 2026-10-01 2026-10-07`
6. Inicie: duplo clique em **Iniciar Painel.bat** ou o comando uvicorn acima.

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
- Streamlit Community Cloud: arquivo principal `streamlit_app.py`; configuração em **Settings > Secrets** no formato de `.streamlit/secrets.toml.example`. `APP_PASSWORD_HASH` (opcional) pede senha para abrir; só o hash PBKDF2 fica guardado. `python scripts/gerar_secrets.py --nova-senha` gera senha nova (em `~/.painel-omie/senha-streamlit.txt`) e o `secrets.toml` com o hash. Após 5 erros a sessão fica bloqueada por 5 min.
- **Modo recomendado (só visualização):** o GitHub Actions (`.github/workflows/publicar.yml`) roda `scripts/publicar_dados.py` a cada 20 min, mesmo com o PC desligado (cada execução agenda a próxima; o cron fica de reserva porque o GitHub atrasa agendamentos). Para pausar, desative o workflow na aba Actions.
- **Painel sempre ativo:** o Streamlit Cloud gratuito suspende apps sem visitas. O workflow `manter-ativo.yml` abre o painel com um navegador (`scripts/manter_ativo.py`) a cada ~2 h, disparado pela publicação, e o acorda se estiver suspenso. O endereço fica no secret `STREAMLIT_APP_URL`. As chaves ficam em **Settings > Secrets and variables > Actions** (`OMIE_APP_KEY`, `OMIE_APP_SECRET`, `PAINEL_DATA_KEY`), nunca no código. O script consulta a Omie (somente leitura), criptografa os dados (Fernet, `PAINEL_DATA_KEY`) e sobrescreve `painel.enc` no branch `dados`. O Streamlit recebe só `PAINEL_DATA_URL` e `PAINEL_DATA_KEY`. Para publicar na hora: aba **Actions > Publicar dados do painel > Run workflow**.
- **Só a filial:** este repositório publica apenas `painel.enc` da JCA Filial. A matriz tem repositório, robô, chave de cifra e app do Streamlit próprios: [FATURAMENTOMATRIZJCA](https://github.com/lelisson/FATURAMENTOMATRIZJCA). No GitHub os secrets da filial se chamam `OMIE_APP_KEY`/`OMIE_APP_SECRET`. `PEDIDOS_MAX_SEG` limita o tempo de ConsultarPedido por execução. Meses fechados (após o dia 1 às 23:59 do mês seguinte, `DIA_FECHAMENTO=2`) ficam congelados em `backend/data/cache_congelado_filial.enc` (cifrado, no cache do Actions) e não são consultados de novo; no **domingo** o robô reconsulta esses meses e atualiza o cache (ou **Run workflow** com "Consultar de novo também os meses fechados"). O script também roda num PC com `.env` (log em `%USERPROFILE%\.painel-omie\publicar.log`).
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
