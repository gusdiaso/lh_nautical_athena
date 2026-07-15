# dbt Project — LH Nautical

Documentação específica do projeto dbt para transformação Bronze → Silver → Gold.

---

## Visão Rápida

| Camada | Diretório | Materialização | Schema | Descrição |
|--------|-----------|----------------|--------|-----------|
| **Staging** | `models/staging/` | `view` | `silver` | Cópia organizada da Bronze (renomeia, tipa) |
| **Intermediate** | `models/intermediate/` | `table` | `silver` | Limpeza, dedup, validação, enriquecimento |
| **Marts** | `models/marts/` | `table` | `gold` | Modelo dimensional (dimensões + fatos) |

---

## Estrutura de Diretórios

```
src/dbt/
├── dbt_project.yml          # Configuração principal
├── models/
│   ├── staging/             # 24 models stg_*
│   │   └── sources.yml      # Definição das sources (Bronze)
│   ├── intermediate/        # 24 models int_*
│   └── marts/               # 13 models dim_*/fact_*
├── macros/                  # Macros reutilizáveis
│   ├── generate_schema_name.sql
│   └── generate_database_name.sql
├── tests/                   # Testes singulares (SQL)
│   ├── int_stock_movements_consistency.sql
│   ├── int_returns_has_refund_amount.sql
│   ├── int_product_variants_metrics_consistency.sql
│   └── int_exchange_rates_consistency.sql
├── analyses/                # Análises ad-hoc (não no DAG)
├── seeds/                   # CSVs versionados (dimensões pequenas)
└── snapshots/               # SCD Type 2 (histórico de mudanças)
```

---

## Convenções

### Nomenclatura de Models

| Prefixo | Camada | Exemplo |
|---------|--------|---------|
| `stg_` | Staging | `stg_customers` |
| `int_` | Intermediate | `int_customers` |
| `dim_` | Marts (Dimensão) | `dim_customers` |
| `fact_` | Marts (Fato) | `fact_order_items` |

### Nomenclatura de Colunas (Marts)

| Prefixo | Significado |
|---------|-------------|
| `sk_` | Surrogate Key (chave substituta, hash) |
| `nk_` | Natural Key (chave natural do sistema origem) |

### SQL Formatting

**Leading Comma** (obrigatório):

```sql
SELECT
    coluna_um
    , coluna_dois
    , coluna_tres
FROM tabela
```

---

## Configuração

### Perfis (`profiles.yml` na raiz do projeto)

```yaml
lh_nautical:
  target: dev
  outputs:
    dev:
      type: databricks
      catalog: dev_lh_nautical
      schema: silver
      host: https://dbc-xxx.cloud.databricks.com
      http_path: "{{ env_var('DBT_HTTP_PATH') }}"
      token: "{{ env_var('DBT_DATABRICKS_TOKEN') }}"
    prod:
      type: databricks
      catalog: prod_lh_nautical
      schema: silver
      host: https://dbc-xxx.cloud.databricks.com
      http_path: "{{ env_var('DBT_HTTP_PATH') }}"
      token: "{{ env_var('DBT_DATABRICKS_TOKEN_PROD') }}"
```

### Variáveis de Ambiente (`.env` na raiz)

```bash
# Dev
DBT_DATABRICKS_TOKEN=seu_token_pessoal
DBT_HTTP_PATH=sql/1.0/warehouses/xxx

# Prod
DBT_DATABRICKS_TOKEN_PROD=token_service_principal
```

---

## Como Rodar

### Desenvolvimento

```bash
# Carregar variáveis
source .env

# Testar conexão
dbt debug

# Rodar todos os models
dbt run

# Rodar apenas staging
dbt run --select staging

# Rodar apenas intermediate
dbt run --select intermediate

# Rodar apenas marts
dbt run --select marts

# Rodar model específico
dbt run --select stg_customers

# Rodar model + downstream
dbt run --select +int_customers

# Testes
dbt test
dbt test --select stg_customers

# Documentação
dbt docs generate
dbt docs serve
```

### Produção

```bash
source .env
dbt debug --target prod
dbt run --target prod
dbt test --target prod
dbt docs generate --target prod
```

---

## Sources (Bronze)

Definidas em `models/staging/sources.yml`:

```yaml
sources:
  - name: bronze
    catalog: "{{ target.catalog }}"
    schema: bronze
    tables:
      - name: customers
      - name: orders
      - name: order_items
      # ... outras 21 tabelas
```

**Uso nos models:**

```sql
-- stg_customers.sql
WITH source AS (
    SELECT * FROM {{ source('bronze', 'customers') }}
)
SELECT
    id AS customer_id
    , person_type
    ...
FROM source
```

---

## Macros Disponíveis

| Macro | Arquivo | Descrição |
|-------|---------|-----------|
| `generate_schema_name` | `macros/generate_schema_name.sql` | Evita concatenação de schema (usa só o `+schema` do dbt_project.yml) |
| `generate_database_name` | `macros/generate_database_name.sql` | Permite sobrescrever catálogo via config do model |

**Documentação completa:** [`docs/macros.md`](../docs/macros.md)

---

## Testes

### Genéricos (em `schema.yml` dos models)

```yaml
models:
  - name: stg_customers
    columns:
      - name: customer_id
        tests:
          - not_null
          - unique
      - name: email
        tests:
          - not_null
      - name: person_type
        tests:
          - accepted_values:
              values: ['PF', 'PJ']
```

### Singulares (arquivos `.sql` em `tests/`)

```sql
-- tests/int_customers_consistency.sql
SELECT *
FROM {{ ref('int_customers') }}
WHERE customer_id IS NULL
   OR email NOT LIKE '%@%'
```

> Se a query retornar linhas → **teste FALHA**.

---

## Seeds (CSVs Versionados)

Para dimensões pequenas que não vêm do ERP:

```
seeds/
├── currency_codes.csv      # Códigos ISO de moedas
├── country_codes.csv       # Códigos ISO de países
└── tax_regimes.csv         # Regimes tributários
```

```bash
dbt seed        # Carrega todos
dbt seed --select currency_codes  # Carrega específico
```

---

## Snapshots (SCD Type 2)

Para rastrear histórico de mudanças em dimensões:

```sql
-- snapshots/scd_customers.sql
{% snapshot scd_customers %}
    {{
        config(
            target_schema='silver',
            unique_key='customer_id',
            strategy='check',
            check_cols=['email', 'phone', 'is_active'],
        )
    }}
    SELECT * FROM {{ ref('int_customers') }}
{% endsnapshot %}
```

```bash
dbt snapshot
```

---

## Documentação (dbt Docs)

```bash
# Gerar
dbt docs generate

# Servir localmente (porta 8080)
dbt docs serve

# Porta customizada
dbt docs serve --port 8081
```

### Documentar Models/Colunas

Em `models/staging/schema.yml` (ou arquivo .yml ao lado do model):

```yaml
models:
  - name: stg_customers
    description: "Clientes vindos da Bronze com colunas renomeadas e tipadas"
    columns:
      - name: customer_id
        description: "Chave primária do cliente (PK)"
        tests:
          - not_null
          - unique
      - name: email
        description: "E-mail de contato do cliente"
```

---

## Variáveis (vars)

No `dbt_project.yml` ou via CLI:

```yaml
vars:
  start_date: '2019-01-01'
  default_exchange_rate: 1.0
```

```bash
# Via CLI
dbt run --vars '{start_date: "2024-01-01"}'
```

**Uso no SQL:**

```sql
WHERE created_at >= '{{ var("start_date") }}'
```

---

## Debugging

### Ver SQL Compilado

```bash
# Arquivo específico
dbt compile --select stg_customers

# Ver no terminal
dbt compile --select stg_customers --inline
```

Arquivos gerados em: `target/compiled/lh_nautical/...`

### Ver Queries Executadas

No Databricks: **Query History** → filtrar por usuário/warehouse

### Logs dbt

```bash
# Debug verbose
dbt run --select stg_customers --log-level DEBUG
```

---

## Performance

### Dicas para Databricks

1. **Use `table` para Intermediate/Marts** — views no Staging apenas
2. **Particione fatos grandes** por data (`partition_by` no config)
3. **Z-Order** nas tabelas Delta para colunas de join/filtro frequentes
4. **Evite `SELECT *`** — liste colunas explicitamente
5. **Use `incremental`** para fatos grandes (ex: `fact_order_items`)

```yaml
# Exemplo: model incremental particionado
models:
  lh_nautical:
    marts:
      fact_order_items:
        +materialized: incremental
        +incremental
        +incremental_strategy: merge
        +unique_key: order_item_id
        +partition_by:
          - field: order_date
            data_type: DATE
```

---

## CI/CD

O pipeline roda no **Bitbucket Pipelines**. Veja [`docs/ci_cd_pipeline.md`](../docs/ci_cd_pipeline.md).

### O que roda no CI

| Stage | Comando |
|-------|---------|
| Lint SQL | `sqlfluff lint src/dbt/` |
| Parse | `dbt parse` |
| Compile | `dbt compile` |
| Testes unitários | `pytest tests/` |
| dbt test (amostra) | `dbt test --select tag:ci` |

---

## Referências Rápidas

| Documento | Link |
|-----------|------|
| Configuração completa dbt | [`docs/dbt_configuration.md`](../docs/dbt_configuration.md) |
| Macros | [`docs/macros.md`](../docs/macros.md) |
| Modelo Dimensional | [`docs/star_schema.md`](../docs/star_schema.md) |
| Dicionário de Dados | [`docs/dictionary.md`](../docs/dictionary.md) |
| CI/CD Pipeline | [`docs/ci_cd_pipeline.md`](../docs/ci_cd_pipeline.md) |
| Orquestração Extração→Transformação | [`docs/transform_after_extract.md`](../docs/transform_after_extract.md) |
| Planejamento & Convenções | [`docs/planejamento_dbt.md`](../docs/planejamento_dbt.md) |

---

## Comandos Úteis (Cheatsheet)

```bash
# Limpar artifacts
dbt clean

# Instalar pacotes (packages.yml)
dbt deps

# Listar models
dbt ls

# Listar models com seleção
dbt ls --select staging

# Ver DAG (dependências)
dbt docs generate && dbt docs serve

# Rodar com target específico
dbt run --target prod

# Seleção avançada
dbt run --select "stg_* +int_customers"      # staging + int_customers + downstream
dbt run --select "@source:bronze +"         # tudo que depende de sources bronze
dbt run --select "tag:daily"                # models com tag daily
dbt run --exclude "fact_*"                  # tudo exceto fatos

# Testes
dbt test --select "tag:critical"            # só testes críticos
dbt test --store-failures                   # salva falhas como tabelas

# Snapshot
dbt snapshot

# Seed
dbt seed --select currency_codes
```

---

## Troubleshooting Comum

| Erro | Solução |
|------|---------|
| `relation does not exist` | Rode `dbt run` upstream primeiro; verifique `ref()` |
| `column does not exist` | Verifique `source()` ou `ref()`; rode `dbt compile` |
| `macro not found` | Verifique `macro-paths` no `dbt_project.yml` |
| `dbt debug` falha | Verifique `.env`, token, HTTP_PATH, warehouse rodando |
| Lento no Databricks | Aumente warehouse size; use table materialization; Z-Order |
| `Incremental` falha | Verifique `unique_key`; veja `target/run_results.json` |

---

## Contribuindo

1. Crie branch: `git checkout -b feat/meu-model`
2. Adicione model em `models/<camada>/`
3. Adicione testes (genéricos no `.yml`, singulares em `tests/`)
4. Documente no `.yml` (description em model e colunas)
5. Rode local: `dbt run --select meu-model && dbt test --select meu-model`
6. Commit: `git commit -m "feat: adiciona stg_nova_tabela"`
7. PR para `develop`