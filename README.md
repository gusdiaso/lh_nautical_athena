# LH Nautical

## Descrição do Projeto

O **LH Nautical** é uma plataforma de dados completa construída no ecossistema **Databricks** para uma rede de varejo náutico com 3 armazéns (centros de distribuição) e 3 lojas. O projeto cobre quatro frentes, em sequência:

| Frente | O que faz | Onde está |
|--------|-----------|-----------|
| **Ingestão** | Extrai 24 tabelas de um ERP SQL Server e cotações USD/EUR da API do Banco Central para tabelas **Delta Lake** (camada Bronze) | `src/ingestion/` |
| **Transformação** | dbt aplica a **Arquitetura Medalhão** (Bronze → Silver → Gold) e entrega um modelo dimensional com 6 dimensões e 6 fatos, mais tabelas de demanda e features para ML (schema `ml`) | `src/dbt/` |
| **Previsão de demanda (ML)** | Prevê a venda dos próximos 3 meses por produto × loja com uma régua estatística e três modelos comparados (Regressão Linear, GLM Poisson/Tweedie, XGBoost), e analisa o crescimento por centro de distribuição e loja | `src/analytics_ai/demand_*.py`, `notebooks/ml/` |
| **RAG documental (Gen AI)** | Responde perguntas em linguagem natural sobre a documentação técnica do projeto, com citações verificáveis, sem acesso ao Data Warehouse | `src/analytics_ai/rag_*.py`, `apps/rag_chat/` |

Tudo roda no Unity Catalog (`dev_lh_nautical` / `prod_lh_nautical`), é declarado como código (Databricks Asset Bundles) e é validado por testes de qualidade no dbt e por testes Python offline.

### Solução de Ingestão

A ingestão é dividida em duas frentes independentes:

| Fonte | Tecnologia | Modo de Carga | Retry |
|-------|-----------|---------------|-------|
| **SQL Server (ERP)** — 24 tabelas operacionais (clientes, produtos, vendas, estoque, compras) | JDBC (`pyspark`) | Full overwrite — cada execução substitui completamente a tabela Bronze | 3 tentativas com backoff exponencial (2s, 4s, 8s) |
| **API PTAX (Banco Central)** — cotações diárias USD/EUR | HTTP (`requests`) | Incremental (merge/upsert) com suporte a `full` para reprocessamento histórico | 3 tentativas com backoff exponencial; retorna vazio em vez de exceção |

**Scripts de ingestão:**
- `src/ingestion/extract_lh_nautical.py` — extração SQL Server, aceita `--table` para executar tabela específica
- `src/ingestion/extract_exchange_rates.py` — extração API BCB, aceita `--load-mode` (incremental | full)

**Metadados:** toda tabela Bronze recebe as colunas `_ingested_at` (timestamp da ingestão) e `_source_path` (origem dos dados).

### Fluxo de Transformação (dbt)

| Camada | Diretório | Materialização | Schema | Descrição |
|--------|-----------|----------------|--------|-----------|
| **Staging** | `src/dbt/models/staging/` | `ephemeral` | — | Cópia organizada da Bronze (renomeia colunas, tipa dados) como CTE nos modelos downstream |
| **Intermediate** | `src/dbt/models/intermediate/` | `table` | `silver` | Limpeza, dedup, validação, enriquecimento |
| **Marts** | `src/dbt/models/marts/` | `table` | `gold` | Modelo dimensional (6 dimensões + 6 fatos) |

O dbt lê as tabelas Bronze via `{{ source('bronze', 'nome_tabela') }}` e aplica a modelagem em cascata: Staging → Intermediate → Marts.

### Diferenciais do Projeto

- **Infraestrutura como Código**: Databricks Asset Bundles (DAB) para declarar jobs e permissões
- **CI/CD**: Pipeline automatizado via Bitbucket Pipelines (deploy em produção)
- **Geração Automática de YAML**: `resources/extract/generate_dab_lh_nautical.py` gera o YAML do job a partir da lista de tabelas em `config.py`
- **Retry Automático**: Tratamento de falhas de conexão com tenacity
- **Agendamento**: Jobs configurados para execução automática diária
- **Testes de Qualidade**: 209+ testes genéricos (not_null, unique, accepted_values) e 36 testes singulares personalizados

### Status do Projeto

| Fase | Descrição | Status |
|------|-----------|--------|
| **Bronze** | Ingestão SQL Server e API BCB para Delta Lake | Implementado |
| **Staging** | Modelos ephemeral (CTE) para organização e tipagem | Implementado |
| **Intermediate** | Tabelas dbt com limpeza, validação e enriquecimento | Implementado |
| **Gold / Marts** | Modelos dimensionais prontos para análise | Implementado |
| **RAG Documental** | Busca em linguagem natural na documentação do projeto (Gen AI) | Implementado |
| **Dashboards** | Visualizações e relatórios | Futuro |
| **Machine Learning** | Previsão de demanda por produto × loja para os próximos 3 meses (régua estatística + Regressão Linear, GLM Poisson/Tweedie e XGBoost comparados); crescimento por centro de distribuição e loja | Implementado |

---

## Navegação Rápida

- [Dependências do Projeto](#dependências-do-projeto)
- [Configuração do Ambiente de Desenvolvimento](#configuração-do-ambiente-de-desenvolvimento)
- [Pipeline Completo (Ingestão → Transformação → Orquestração → ML → RAG)](#passo-a-passo-pipeline-completo)
- [Previsão de Demanda (ML)](#previsão-de-demanda-ml)
- [RAG Documental](#rag-documental)
- [Comandos Úteis](#comandos-úteis)
- [Estrutura do Projeto](#estrutura-do-projeto)
- [Arquitetura](#arquitetura)
- [Documentação](#documentação)
- [Referências](#referências)
- [Boas Práticas e Dicas](#boas-práticas-e-dicas)

---

## Dependências do Projeto

### Python (execução local)

Todas as dependências Python estão em [`requirements.txt`](requirements.txt) na raiz. As principais categorias são:

| Categoria | Principais Pacotes | Versão |
|-----------|-------------------|--------|
| **Processamento Spark** | `pyspark`, `delta-spark`, `databricks-connect`, `pyarrow` | 4.1, 4.3, 18.3, 24.0 |
| **dbt + Databricks** | `dbt-core`, `dbt-databricks`, `dbt-spark`, `dbt-adapters` | 1.11, 1.12, 1.10, 1.22 |
| **APIs HTTP** | `requests` | 2.34 |
| **Manipulação de Dados** | `pandas`, `numpy` | 2.3, 2.5 |
| **Retry Automático** | `tenacity` | 9.1 |
| **Linter SQL** | `sqlfluff`, `sqlfluff-templater-dbt` | 4.2 |
| **Testes** | `pytest` | 9.1 |
| **Machine Learning** | `scikit-learn` (GLM Poisson/Tweedie), `xgboost`, `matplotlib` (gráficos dos notebooks) | 1.9, 3.0, 3.11 |
| **Databricks SQL** | `databricks-sql-connector` | 4.2 |
| **Utilidades** | `python-slugify`, `openpyxl`, `deepdiff`, `tqdm` | — |

### dbt (pacotes)

Definidos em [`packages.yml`](packages.yml):

| Pacote | Versão | Uso |
|--------|--------|-----|
| `dbt-labs/dbt_utils` | 1.1.1 | Macros utilitárias (generate_surrogate_key, date_spine, etc.) |

### Ambientes separados

| Ambiente | Arquivo | Por quê |
|----------|---------|---------|
| Aplicação RAG (Streamlit) | [`apps/rag_chat/requirements.txt`](apps/rag_chat/requirements.txt) | A App do Databricks instala só o que a interface precisa |
| Jobs RAG no Databricks | `resources/rag/*.yml` (bibliotecas do job) | O SDK `databricks-ai-search` exige `protobuf < 6` e o dbt exige `protobuf >= 6`; por isso ele não entra no `requirements.txt` |

---

## Configuração do Ambiente de Desenvolvimento

### Pré-requisitos

| Ferramenta | Versão Mínima | Instalação (Windows) |
|------------|---------------|----------------------|
| [Python](https://www.python.org/downloads/) | 3.12 | `winget install Python.Python.3.12` |
| [Git](https://git-scm.com/downloads) | — | `winget install Git.Git` |
| [Databricks CLI](https://docs.databricks.com/en/dev-tools/cli/tutorial.html) | 1.x | `winget install Databricks.DatabricksCLI` |

### Ambiente Virtual e Dependências

```bash
# Clonar o repositório
git clone <url-do-repositorio>
cd lh_nautical

# Criar e ativar ambiente virtual (Windows)
python -m venv .venv
.venv\Scripts\Activate.ps1

# Instalar dependências Python
pip install -r requirements.txt

# Instalar pacotes dbt
dbt deps
```

### Autenticação Databricks

```bash
# Login interativo na CLI (abre navegador)
databricks auth login --host https://<url-do-workspace>

# Verificar autenticação
databricks auth token --host https://<url-do-workspace>
```

> A URL do workspace tem o formato `https://dbc-xxxxx-xxxx.cloud.databricks.com`.

### Variáveis de Ambiente

Crie o arquivo `.env` na raiz do projeto:

```env
# Dev — seu token pessoal do Databricks
DBT_DATABRICKS_TOKEN=seu_token_aqui
DBT_HTTP_PATH=sql/1.0/warehouses/seu_warehouse_id

# Prod — token da Service Principal
DBT_DATABRICKS_TOKEN_PROD=token_da_sp_aqui

# Databricks Connect (para testes locais)
DATABRICKS_HOST=https://<url-do-workspace>
DATABRICKS_TOKEN=<seu-token>
```

> O `.env` já está no `.gitignore`. Para gerar o token da Service Principal, veja [docs/dbt_configuration.md](docs/dbt_configuration.md).

### Segredos (uma única vez)

```bash
# Criar scope de segredos no Databricks
databricks secrets create-scope --scope lh_nautical

# Adicionar senha do SQL Server
databricks secrets put --scope lh_nautical --key secret_lh_nautical_bd

# Tokens usados pelo job dbt_transform (src/dbt/run_dbt_step.py).
# O secret _prod é obrigatório para --target prod.
databricks secrets put-secret lh_nautical dbt_http_path
databricks secrets put-secret lh_nautical dbt_databricks_token
databricks secrets put-secret lh_nautical dbt_databricks_token_prod
```

### Verificar Configuração

```bash
# Validar o bundle DAB
databricks bundle validate

# Testar conexão dbt
source .env
dbt debug

# Rodar testes unitários (sem Databricks)
pytest tests/ -v
```

---

## Passo a Passo: Pipeline Completo

Ordem de execução de ponta a ponta: **ingestão → transformação → orquestração → previsão de demanda → RAG**. Os passos 1 a 6 preparam o Data Warehouse; o 7 automatiza isso; o 8 e o 9 dependem das tabelas Gold e `ml` já materializadas.

### 1. Deploy do Bundle

```bash
# Desenvolvimento
databricks bundle deploy --target dev

# Produção (após testar no dev)
databricks bundle deploy --target prod
```

### 2. Executar Ingestão — Bronze

```bash
# Extrair 24 tabelas do SQL Server
databricks bundle run extract_lh_nautical --target dev

# Extrair cotações USD/EUR da API do BCB
databricks bundle run extract_exchange_rates --target dev
```

> Para extrair uma tabela específica do SQL Server: `databricks bundle run extract_lh_nautical --target dev -- --table customers`

### 3. Executar Transformação — dbt (Silver + Gold)

```bash
# Carregar variáveis de ambiente
source .env

# Opção A: rodar todas as camadas de uma vez
dbt run

# Opção B: rodar camada por camada (recomendado para debug)
dbt run --select staging
dbt run --select intermediate
dbt run --select marts

# Opção C: rodar modelo específico + downstream
dbt run --select stg_customers
dbt run --select +int_customers
```

### 4. Validar Qualidade dos Dados

```bash
# Rodar todos os testes
dbt test

# Testar apenas uma camada
dbt test --select staging
dbt test --select intermediate
dbt test --select marts

# Testar modelo específico
dbt test --select stg_customers

# Salvar falhas como tabelas para inspeção
dbt test --store-failures
```

### 5. Gerar Documentação

```bash
dbt docs generate
dbt docs serve   # Acessar em http://localhost:8080
```

### 6. Verificar Resultados

| Camada | Catálogo | Schema | O que contém |
|--------|----------|--------|-------------|
| **Bronze** | `dev_lh_nautical` | `bronze` | 24 tabelas operacionais (inclui `fiscal_invoices`) + `exchange_rates` |
| **Staging** | — | — | Injetado como CTE nos modelos Intermediate (não materializado) |
| **Intermediate** | `dev_lh_nautical` | `silver` | 24 tabelas limpas, validadas e enriquecidas |
| **Gold / Marts** | `dev_lh_nautical` | `gold` | 6 dimensões + 6 fatos (modelo dimensional) |
| **ML** | `dev_lh_nautical` | `ml` | Demanda agregada (dia/semana/mês/trimestre), índice sazonal e tendência por corte, painel de cortes, tabela de features e tabelas de previsão |

### 7. Orquestração (execução automática)

O job `orchestrator_transform` encadeia tudo o que está acima — extração → validação → column masking → `dbt build` — e roda todo dia às 23:00. Para disparar manualmente:

```bash
databricks bundle run orchestrator_transform --target dev
```

Detalhes das dependências entre jobs em [`docs/orquestracao_transform.md`](docs/orquestracao_transform.md).

### 8. Previsão de demanda (ML)

Com a camada Gold pronta, os modelos dbt do diretório `ml/` constroem a tabela de features e os scripts treinam e gravam as previsões:

```bash
# Tabelas de demanda, sazonalidade/tendência e features (schema ml)
dbt build --select ml

# GLM Poisson (modelo candidato): treina, prevê e grava as duas tabelas Delta de previsão
PYTHONPATH=. python -m src.analytics_ai.run_demand_glm --model-name glm_poisson

# Variante Tweedie, na mesma tabela, em partição própria
PYTHONPATH=. python -m src.analytics_ai.run_demand_glm --model-name glm_tweedie --family tweedie --power 1.3

# XGBoost (escreve CSVs de teste, previsão, métricas e busca de validação)
PYTHONPATH=. python -m src.analytics_ai.run_demand_xgboost
```

Localmente os scripts usam Databricks Connect (`DATABRICKS_PROFILE`); no workspace, os notebooks em `notebooks/ml/` (01 a 08) reproduzem análise, modelos e a análise de crescimento por CD/PDV, nessa ordem. Veja [Previsão de Demanda (ML)](#previsão-de-demanda-ml).

### 9. RAG documental

Depois de qualquer mudança na documentação: copiar os arquivos para o Volume, reindexar e conferir a saúde do índice (comandos em [RAG Documental](#rag-documental)).

---

## Previsão de Demanda (ML)

**Pergunta de negócio:** quanto cada produto vai vender em cada loja nos próximos 3 meses, e qual centro de distribuição cresce mais.

**Como foi resolvido.** A demanda por produto × loja × mês tem 79% de meses sem venda, então o alvo passou a ser a **soma dos 3 meses seguintes** (50% de zeros). A análise exploratória (notebooks 01 a 04) mostrou que o sinal previsível está no nível **categoria × loja**, com sazonalidade forte e crescimento de ~15% ao ano — e que o histórico de um produto isolado quase não prevê o futuro dele. Isso virou uma **régua** (média da categoria na loja × índice sazonal × fator de tendência) e uma tabela de features (`ml_features_produto_loja_mes`, 33 colunas) sobre a qual três modelos foram comparados em 12 cortes temporais de teste (06/2025 a 05/2026), sempre com validação separada e leitura única do teste.

| Modelo | Erro por produto × loja (WAPE) | Erro por categoria × loja | Viés | Veredito |
|--------|-------------------------------|---------------------------|------|----------|
| Régua (referência) | 86,6% | 11,9% | −2,8% | A nota a superar |
| Regressão Linear | 85,8% | 12,6% | −7,7% | Não supera a régua |
| **GLM Poisson** | 87,0% | **11,8%** | **+0,1%** | Empata no erro e elimina o viés — modelo candidato |
| GLM Tweedie (power 1,3) | 87,0% | 11,8% | −0,05% | Igual ao Poisson |
| XGBoost calibrado | 85,9% | 15,6% | −10,9% | Não supera a régua |

**Leitura:** nenhum modelo reduz o erro de forma relevante — o que separa um produto que vende 0 de um que vende 20 não está nos dados antes da venda. O GLM Poisson é o candidato por entregar a mesma precisão da régua **sem viés** e com a previsão mês a mês pronta. Os dois modelos que parecem melhores por produto (Linear, XGBoost) estão prevendo sistematicamente abaixo do real.

**Crescimento por centro de distribuição e loja (set–nov/2026):** em unidades, o Armazém Camargo e a Loja Oliveira lideram, mas o crescimento percentual é o mesmo em todas as unidades (89,8%) por construção do índice sazonal; frente ao mesmo trimestre de 2025, o CD que mais cresce é o **Armazém Novaes** (+9,6%) e a loja é a **Oliveira** (+31,5%).

| Onde está | Conteúdo |
|-----------|----------|
| [`docs/previsao_demanda_produto_loja.md`](docs/previsao_demanda_produto_loja.md) | Relatório completo: problema, análises, régua, features, os três modelos, crescimento por CD/PDV, decisões e limitações |
| [`docs/dicionario_features_ml_produto_loja_mes.md`](docs/dicionario_features_ml_produto_loja_mes.md) | Dicionário das 33 colunas da tabela de features |
| [`docs/xgboost_demand.md`](docs/xgboost_demand.md) | Recorte, variantes e execução do XGBoost |
| [`docs/expansao_rede_distribuicao.md`](docs/expansao_rede_distribuicao.md) | Expansão da rede: onde abrir o próximo ponto de distribuição (notebook 09, `network_expansion.py`) |
| `notebooks/ml/` (01 a 08) | EDA (01–03), régua (04), Regressão Linear (05, 05b), GLM (06), XGBoost (07), crescimento por CD/PDV (08), expansão da rede (09) |
| `dev_lh_nautical.ml.ml_forecast_demanda_3m` / `ml_forecast_demanda_mensal` | Tabelas Delta de previsão, particionadas por `model_name` |
| `tests/test_demand_*.py`, `test_eda_seasonality.py`, `test_ml_config.py` | Testes offline (pandas puro) da régua, do GLM, do XGBoost, da análise de crescimento e das configurações |

---

## RAG Documental

O projeto possui um RAG que responde perguntas em linguagem natural **somente
sobre a documentação técnica versionada**. Ele não consulta Bronze, Silver ou
Gold, não gera SQL e recusa perguntas que peçam valores do Data Warehouse.

Os recursos ficam em um schema próprio (`dev_lh_nautical.rag`): Volume com os
documentos aprovados, tabela Delta de chunks e índice Delta Sync Hybrid.

### Jobs disponíveis

| Job | O que faz | Quando rodar |
|-----|-----------|--------------|
| `rag_ingestion` | Lê a allowlist, sanitiza, divide em chunks, sobrescreve o Delta e sincroniza o índice | Sempre que a documentação aprovada mudar |
| `rag_health_check` | Prontidão do índice, deriva de linhas, latência e isolamento do warehouse | Após a ingestão e antes de apresentar |
| `rag_evaluation` | Executa uma suíte do Golden Dataset e grava o relatório | `smoke` no dia a dia, `full` em marcos |
| `rag_demo` | Uma pergunta documental end-to-end com citações conferidas | Demonstração ao vivo |

```bash
# Ingestão da documentação aprovada
databricks bundle run rag_ingestion -t dev

# Verificação operacional e de isolamento
databricks bundle run rag_health_check -t dev

# Avaliação: 10 casos rápidos ou os 35 casos completos
databricks bundle run rag_evaluation -t dev --params suite=smoke
databricks bundle run rag_evaluation -t dev --params suite=full

# Demonstração
databricks bundle run rag_demo -t dev
```

### Corpus indexado e como atualizá-lo

O corpus é a allowlist `DEFAULT_ALLOWED_PATHS` em [`src/analytics_ai/rag_documents.py`](src/analytics_ai/rag_documents.py): o `README.md`, o `src/dbt/README.md` e os documentos de `docs/` sobre ingestão, dbt, modelo dimensional, orquestração, CI/CD, previsão de demanda e o próprio RAG. Cada arquivo é dividido por cabeçalho Markdown em chunks de até 800 caracteres, que carregam o caminho de títulos (`CONTEXTO: Documento > Seção > Subseção`) e repetem o cabeçalho de uma tabela quando a cortam — por isso os documentos usam títulos descritivos e seções curtas.

O job de ingestão lê o Volume `/Volumes/dev_lh_nautical/rag/documents`, que precisa espelhar o repositório. Depois de alterar ou incluir um documento:

```bash
# 1. Copiar os arquivos alterados para o Volume (mesmo caminho relativo do repositório)
databricks fs cp README.md dbfs:/Volumes/dev_lh_nautical/rag/documents/README.md --overwrite
databricks fs cp docs/previsao_demanda_produto_loja.md dbfs:/Volumes/dev_lh_nautical/rag/documents/docs/previsao_demanda_produto_loja.md --overwrite

# 2. Reindexar (sobrescreve a tabela de chunks e sincroniza o índice)
databricks bundle run rag_ingestion -t dev

# 3. Conferir prontidão, deriva de linhas e isolamento
databricks bundle run rag_health_check -t dev
```

Um documento novo só entra no índice se estiver na allowlist **e** no Volume. A avaliação (`rag_evaluation`) referencia pares documento/seção do Golden Dataset — renomear um desses títulos quebra a suíte, então mudanças de cabeçalho passam por `python -m analytics_ai.rag_evaluation validate`.

### Validação local (sem Databricks)

```bash
# Testes offline do RAG
python -m unittest tests.test_rag_documents tests.test_rag_endpoint tests.test_rag_evaluation tests.test_rag_groundedness tests.test_rag_operations

# Validação do Golden Dataset e da cobertura do corpus
PYTHONPATH=src python -m analytics_ai.rag_evaluation validate --suite full
```

> ℹ️ O SDK `databricks-ai-search` não entra no `requirements.txt` principal:
> ele exige `protobuf < 6` e o dbt do projeto exige `protobuf >= 6`. A
> dependência é declarada apenas no ambiente dos jobs RAG.

---

## Comandos Úteis

### Deploy e Jobs

```bash
databricks bundle validate          # Validar sintaxe do bundle
databricks bundle plan --target dev # Ver plano de deploy
databricks bundle deploy --target dev   # Deploy em dev
databricks bundle deploy --target prod  # Deploy em prod
databricks bundle run extract_lh_nautical --target dev
databricks bundle run extract_exchange_rates --target dev
databricks bundle destroy --target dev  # Destruir recursos (cuidado!)
```

### dbt

```bash
dbt debug                           # Testar conexão
dbt run                             # Rodar todos os models
dbt run --target prod               # Rodar em produção
dbt test                            # Rodar todos os testes
dbt test --store-failures           # Salvar falhas como tabelas
dbt docs generate && dbt docs serve # Gerar e servir documentação
dbt deps                            # Instalar pacotes (packages.yml)
dbt clean                           # Limpar artifacts compilados
dbt ls                              # Listar todos os models
dbt compile --select stg_customers  # Ver SQL compilado de um model
dbt seed                            # Carregar seeds (CSVs versionados)
dbt snapshot                        # Executar snapshots (SCD Type 2)
```

### Seleção Avançada dbt

```bash
dbt run --select "stg_* +int_customers"        # staging + int_customers + downstream
dbt run --select "@source:bronze +"           # tudo que depende das sources bronze
dbt run --select "tag:daily"                   # models com tag daily
dbt run --exclude "fact_*"                     # tudo exceto fatos
```

### Testes Unitários (Python)

```bash
# Testes sem conexão Databricks
pytest tests/ -v

# Testes com conexão Databricks (requer compute ativo)
pytest tests/ -v --databricks
```

### Linter SQL

```bash
sqlfluff lint src/dbt/              # Verificar formatação SQL
sqlfluff fix src/dbt/               # Corrigir formatação automaticamente
```

---

## Estrutura do Projeto

```
lh_nautical/
├── databricks.yml                         # Config principal do DAB
├── dbt_project.yml                        # Config dbt (models, schemas)
├── profiles.yml                           # Conexão dbt → Databricks
├── .env                                   # Variáveis de ambiente (não versionado)
├── bitbucket-pipelines.yml                # Pipeline CI/CD
├── requirements.txt                       # Dependências Python
├── resources/
│   ├── extract/
│   │   ├── extract_lh_nautical.yml        # Job: SQL Server → Bronze
│   │   ├── extract_exchange_rates.yml     # Job: API BCB → Bronze
│   │   └── generate_dab_lh_nautical.py    # Gerador automático do YAML
│   ├── transform/
│   │   └── dbt_transform.yml              # Job: transformação dbt
│   ├── orchestrator/
│   │   └── orchestrator_transform.yml     # Job: orquestrador principal
│   ├── rag/
│   │   ├── rag_ingestion.yml              # Job: documentação → Delta → índice
│   │   ├── rag_evaluation.yml             # Job: suíte do Golden Dataset
│   │   ├── rag_health_check.yml           # Job: saúde do índice e isolamento
│   │   └── rag_demo.yml                   # Job: demonstração end-to-end
│   └── security/
│       ├── apply_bronze_masks.py          # Script para aplicar masks na Bronze
│       ├── rag_least_privilege.sql        # SQL de menor privilégio do RAG
│       └── apply_rag_grants.py            # Script para aplicar/verificar os grants
├── src/
│   ├── ingestion/
│   │   ├── config.py                      # Constantes (tabelas, JDBC URL)
│   │   ├── utils.py                       # Funções compartilhadas (Spark, Delta)
│   │   ├── extract_lh_nautical.py         # Extração SQL Server
│   │   ├── extract_exchange_rates.py      # Extração API BCB
│   │   └── validate_extraction.py         # Validador pós-extração
│   ├── dbt/                               # Transformações dbt
│   │   ├── run_dbt_step.py                # Wrapper para execução dbt
│   │   ├── models/
│   │   │   ├── staging/                   # Cópia organizada dos dados brutos
│   │   │   ├── intermediate/              # Limpeza e validação
│   │   │   ├── marts/                     # Modelo dimensional (Gold)
│   │   │   └── ml/                        # Demanda agregada e features de ML (schema ml)
│   │   ├── macros/                        # Funções reutilizáveis
│   │   └── tests/                         # Testes de qualidade
│   └── analytics_ai/                      # RAG documental (Gen AI) e previsão de demanda (ML)
│       ├── rag_documents.py               # Allowlist, sanitização e chunking
│       ├── rag_prompt.py                  # Guardrails e contexto delimitado
│       ├── rag_databricks.py              # Delta, índice Delta Sync e retrieval
│       ├── rag_generation.py              # Geração e verificação de citações
│       ├── rag_endpoint.py                # Pacing e retry de rate limit
│       ├── rag_evaluation.py              # Golden Dataset e métricas
│       ├── rag_groundedness.py            # LLM-as-a-judge de fundamentação
│       ├── rag_operations.py              # Saúde do índice e isolamento
│       ├── run_rag_*.py                   # Entrypoints dos jobs RAG
│       ├── demand_*.py                    # Régua, GLM, XGBoost, métricas e gravação das previsões
│       ├── eda_*.py                       # Análise exploratória da demanda (notebooks 01 a 04)
│       ├── network_expansion.py           # Expansão da rede: distância, ganho de um ponto novo, ranking
│       ├── ml_config.py                   # Nomes das tabelas de ML
│       └── run_demand_*.py                # Entrypoints de treino do GLM e do XGBoost
├── notebooks/ml/                          # 01-03 EDA · 04 régua · 05/05b Linear · 06 GLM · 07 XGBoost · 08 crescimento CD/PDV · 09 expansão da rede
├── apps/rag_chat/                         # Interface Streamlit do RAG (app.py, app.yaml, prepare_release.py)
├── evaluation/
│   └── rag_golden_dataset.jsonl           # 35 casos de avaliação do RAG
├── docs/                                  # Documentação (31 arquivos; ver seção Documentação)
└── tests/
    ├── test_rag_*.py                      # Testes offline do RAG (sem Databricks)
    ├── test_demand_*.py, test_ml_config.py, test_run_demand_*.py, test_eda_seasonality.py  # Testes offline de ML
    ├── notebooks/                         # Notebooks de teste
    └── sql/                               # Scripts SQL de teste
```

---

## Arquitetura

```
SQL Server (ERP)                API PTAX (BCB)
       │                              │
       ▼ ─── JDBC (full)              ▼ ─── HTTP (incremental)
┌─────────────────────────┐    ┌─────────────────────────┐
│    BRONZE (ATUAL)       │    │    BRONZE (ATUAL)       │
│  24 tabelas Delta Lake  │    │  exchange_rates Delta   │
└───────────┬─────────────┘    └───────────┬─────────────┘
            │                              │
            └──────────────┬───────────────┘
                           │
                           ▼ ─── dbt
                   ┌─────────────────┐
                   │     SILVER      │
                   │ staging/int.    │
                   │    (dbt)        │
                   └────────┬────────┘
                            │
                            ▼ ─── dbt
                   ┌─────────────────┐
                   │      GOLD       │
                   │     marts       │
                   │    (dbt)        │
                   └────────┬────────┘
                            │
                            ├── → Dashboards
                            ├── → Machine Learning
                            └── → Gen AI
```

---

## Documentação

Tudo em `docs/`. Os documentos marcados com ✦ fazem parte do corpus do RAG.

**Projeto e arquitetura**

| Documento | Descrição |
|-----------|-----------|
| `docs/documento_projeto_lh_nautical.md` ✦ | Documento oficial do projeto — visão executiva completa |
| `docs/relatorio_analise_projeto.md` ✦ | Relatório técnico detalhado com decisões e regras de negócio |
| `docs/planejamento_dbt.md` | Planejamento, cronograma e convenções do projeto dbt |
| `docs/relatorio_resultados_dbt.md` | Resultados da implementação e validação das melhorias do dbt |

**Ingestão e orquestração**

| Documento | Descrição |
|-----------|-----------|
| `docs/extract_lh_nautical.md` ✦ | Extração SQL Server → Bronze (uso, retry, troubleshooting) |
| `docs/extract_exchange_rates.md` ✦ | Extração API BCB → Bronze |
| `docs/orquestracao_transform.md` ✦ | Orquestração dos jobs e dependências entre camadas |
| `docs/transform_after_extract.md` ✦ | Como rodar a transformação logo após a extração |
| `docs/dab_configuration.md` ✦ | Configuração do DAB, targets e governança |
| `docs/ci_cd_pipeline.md` ✦ | CI/CD completo e Service Principal de produção |

**Modelagem dbt e dados**

| Documento | Descrição |
|-----------|-----------|
| `docs/dictionary.md` ✦ | Dicionário de dados (24 tabelas fonte + exchange_rates, colunas, relacionamentos) |
| `docs/star_schema.md` ✦ | Modelo dimensional completo (Star Schema) |
| `docs/mapeamento_dependencias.md` ✦ | Dependências entre modelos, por camada e ordem de execução |
| `docs/dbt_configuration.md` ✦ | Configuração do dbt, profiles e macro de schema |
| `docs/staging.md` ✦ · `docs/intermediate.md` ✦ · `docs/marts.md` ✦ | As três camadas do dbt |
| `docs/marts_tests.md` ✦ | Estratégia de testes da camada Marts |
| `docs/macros.md` ✦ | Documentação das macros dbt |
| `src/dbt/README.md` ✦ | Guia do projeto dbt |

**Previsão de demanda (ML)**

| Documento | Descrição |
|-----------|-----------|
| `docs/previsao_demanda_produto_loja.md` ✦ | Problema, análises, régua, features, comparação dos modelos e crescimento por CD/PDV |
| `docs/dicionario_features_ml_produto_loja_mes.md` ✦ | Dicionário das 33 colunas da tabela de features |
| `docs/xgboost_demand.md` ✦ | XGBoost de demanda: recorte, variantes, resultado e execução |
| `docs/expansao_rede_distribuicao.md` ✦ | Expansão da rede: onde abrir o próximo ponto de distribuição (UF e tipo), distância e ganho por candidato |

**RAG documental**

| Documento | Descrição |
|-----------|-----------|
| `docs/implementacao-rag-documental-databricks.md` ✦ | Arquitetura completa do RAG, decisões e limitações |
| `docs/rag_evaluation.md` ✦ | Golden Dataset, métricas e groundedness |
| `docs/rag_operacao.md` ✦ | Operação: health check, ciclo de vida e falhas |
| `docs/rag_seguranca.md` ✦ | Menor privilégio e isolamento do Data Warehouse |
| `docs/rag_interface_interna.md` ✦ | Interface Streamlit e empacotamento da release |
| `docs/rag_app_producao.md` ✦ | Aplicação publicada no Databricks Apps e seus recursos |
| `docs/rag_mvp.md` | Escopo do MVP inicial |
| `docs/rag_operacao_seguranca_changelog.md` | Changelog da branch de operação e segurança |

> ℹ️ A tabela `fiscal_invoices` é extraída para Bronze mas não possui modelo dbt, pois não integra o modelo dimensional atual.

---

## Referências

- [Databricks Asset Bundles](https://docs.databricks.com/en/dev-tools/bundles/index.html)
- [Databricks CLI](https://docs.databricks.com/en/dev-tools/cli/tutorial.html)
- [Databricks Secrets](https://docs.databricks.com/en/security/secrets/index.html)
- [API PTAX Banco Central](https://olinda.bcb.gov.br/olinda/servico/PTAX)

---

## Boas Práticas e Dicas

### Convenções de Código SQL

O projeto adota a convenção **leading comma** para formatação de queries SQL:

```sql
SELECT
    coluna_um
    , coluna_dois
    , coluna_tres
FROM tabela
WHERE condicao = 'valor'
```

**Por que leading comma?**
- Facilita a inclusão/remoção de colunas sem alterar linhas anteriores
- Melhora a revisão de código no Git (diff mais limpo)
- Padrão adotado pelo time para manter consistência

### Git

```bash
# Criar branch para trabalhar (nunca trabalhe na main)
git checkout -b feat/minha-feature

# Adicionar arquivos específicos (evite git add .)
git add src/ingestion/extract_lh_nautical.py

# Commit com mensagem descritiva
git commit -m "feat: adiciona parametrização no script de extração"
```

**Convenção de mensagens:**

| Prefixo | Uso |
|---------|-----|
| `feat` | Nova funcionalidade |
| `fix` | Correção de bug |
| `chore` | Tarefa de manutenção |
| `docs` | Documentação |
| `refactor` | Mudança sem alterar comportamento |

> O diretório `.databricks/` está no `.gitignore` — é gerado localmente pela CLI e **nunca** deve ser versionado.

### Segurança

- **Nunca** versione senhas, tokens ou URLs internas
- Use **Databricks Secrets** para credenciais de banco de dados
- No target `prod`, configure uma **Service Principal** em vez de usar seu usuário pessoal

### Deploy

- Sempre faça deploy e teste no `dev` antes de ir para o `prod`
- Use `databricks bundle validate` para verificar erros de sintaxe
- Revise o plano com `databricks bundle plan` antes de aplicar

### Retry Automático

Os scripts de extração possuem retry automático via biblioteca `tenacity`:

| Componente | Tentativas | Espera | Exceções |
|------------|------------|--------|----------|
| SQL Server | 3 | Exponencial (2s, 4s, 8s) | Qualquer Exception |
| API PTAX | 3 | Exponencial (2s, 4s, 8s) | RequestException, Timeout |

### Agendamento dos Jobs

Os jobs rodam automaticamente conforme configuração nos YAMLs:

| Job | Horários | Frequência |
|-----|----------|------------|
| orchestrator_transform (pipeline completo) | 23:00 | 1x ao dia |
| extract_lh_nautical | Disparado pelo orchestrator | Sob demanda |
| extract_exchange_rates | Disparado pelo orchestrator | Sob demanda |
| dbt_transform | Disparado pelo orchestrator | Sob demanda |

### CI/CD (Bitbucket)

O pipeline `bitbucket-pipelines.yml` executa automaticamente ao fazer push na branch `main`:

1. Instala a CLI do Databricks
2. Faz deploy em produção (`databricks bundle deploy -t prod`)
3. Roda os jobs de extração (`databricks bundle run ...`)

**Autenticação:** Via variáveis de ambiente do Bitbucket (`DATABRICKS_HOST`, `DATABRICKS_CLIENT_ID`, `DATABRICKS_CLIENT_SECRET`) — nunca no código.

**Nota:** O pipeline atual não executa `dbt test` automaticamente. A transformação dbt (Silver e Gold) é orquestrada pelo job `orchestrator_transform` no Databricks, que executa extração → validação → column masking → transformação dbt em sequência.

---

## Segurança — Column Masking (Dados Sensíveis)

O projeto utiliza **Column Masking** do Unity Catalog para proteger dados sensíveis em todas as camadas. A máscara é aplicada em query time — apenas usuários do grupo `lh_nautical_dev` enxergam os valores reais, tanto no catálogo `dev` quanto no `prod`. Qualquer outro grupo, incluindo `lh_nautical_prod`, sempre vê os valores mascarados nos dois catálogos.

### Colunas Protegidas por Camada

| Camada | Tabela | Colunas | Função |
|--------|--------|---------|--------|
| **Bronze** | `bronze.customers` | `tax_id`, `email`, `phone` | `mask_full`, `mask_email`, `mask_phone` |
| | `bronze.employees` | `cpf`, `email` | `mask_cpf`, `mask_email` |
| | `bronze.suppliers` | `tax_id`, `email`, `phone` | `mask_full`, `mask_email`, `mask_phone` |
| **Silver** | `silver.int_customers` | `tax_id`, `email`, `phone` | `mask_full`, `mask_email`, `mask_phone` |
| | `silver.int_employees` | `cpf`, `email` | `mask_cpf`, `mask_email` |
| | `silver.int_suppliers` | `tax_id`, `email`, `phone` | `mask_full`, `mask_email`, `mask_phone` |
| **Gold** | `gold.dim_customers` | `tax_id`, `email`, `phone` | `mask_full`, `mask_email`, `mask_phone` |
| | `gold.dim_employees` | `cpf`, `email` | `mask_cpf`, `mask_email` |
| | `gold.dim_suppliers` | `tax_id`, `email`, `phone` | `mask_full`, `mask_email`, `mask_phone` |


### Como Funciona

- As funções de máscara ficam no schema `gold` (acessível a todos)
- `mask_full`: oculta completamente (`***MASKED***`)
- `mask_cpf`: oculta completamente (`***MASKED***`)
- `mask_email`: oculta completamente (`***MASKED***`)
- `mask_phone`: oculta completamente (`***MASKED***`)
- Apenas membros do grupo `lh_nautical_dev` enxergam valores reais em qualquer função — o grupo verificado é fixo, independente do catálogo (`dev` ou `prod`); `lh_nautical_prod` nunca vê dado real

---

> Para mais detalhes sobre a orquestração extração → transformação, veja [docs/transform_after_extract.md](docs/transform_after_extract.md).