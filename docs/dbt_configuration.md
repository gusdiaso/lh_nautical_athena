# Configuração do dbt

## Visão Geral

O projeto dbt se conecta ao Databricks Unity Catalog e organiza os dados em 3 camadas:

```
Bronze (dados brutos) → Staging → Intermediate → Marts (Gold)
```

---

## Arquivos de Configuração

### 1. `profiles.yml` — Conexão

Define **como** o dbt conecta no Databricks.

| Campo | O que faz |
|---|---|
| `catalog` | Qual catálogo usar (`dev_lh_nautical` ou `prod_lh_nautical`) |
| `schema` | Schema padrão (sobrescrito pelo dbt_project.yml) |
| `host` | Endpoint do workspace Databricks |
| `http_path` | Caminho do SQL Warehouse (via variável de ambiente) |
| `token` | Token de autenticação (via variável de ambiente) |

**Targets:**
- `dev` → usa `dev_lh_nautical` com seu token pessoal
- `prod` → usa `prod_lh_nautical` com token da Service Principal

### 2. `dbt_project.yml` — Regras por Camada

Define **o que** criar para cada camada do projeto.

```yaml
models:
  lh_nautical:
    staging:
      +schema: silver        # cria em dev_lh_nautical.silver
      +materialized: view    # cria como VIEW

    intermediate:
      +schema: silver        # cria em dev_lh_nautical.silver
      +materialized: table   # cria como TABLE

    marts:
      +schema: gold          # cria em dev_lh_nautical.gold
      +materialized: table   # cria como TABLE
```

**Por que staging é view e intermediate é table?**
- **Staging** → view porque é apenas uma cópia organizada dos dados brutos. Não precisa de performance, só de organização.
- **Intermediate** → table porque aplica limpeza, dedup e validação. Precisa de performance para consultas.
- **Marts** → table porque são tabelas finais para consumo de BI/analistas.

### 3. `generate_schema_name.sql` — Macro

Sem essa macro, o dbt concatenaria: `bronze_silver` (schema do profile + schema customizado).
Com ela, usa só o schema definido em `+schema`: `silver`.

Resultado final: `dev_lh_nautical.silver.stg_stock_movements`

### 4. `sources.yml` — Fontes de Dados

Define de **onde** ler os dados brutos (Bronze).

```yaml
sources:
  - name: bronze
    schema: bronze    # lê de dev_lh_nautical.bronze.*
```

Não precisa de `catalog` porque herda do target ativo.

---

## Fluxo Completo

```
profiles.yml          →  catalog: dev_lh_nautical
dbt_project.yml       →  +schema: silver
macro                 →  usa só o schema (não concatena)
                        = dev_lh_nautical.silver.stg_*
```

---

## Variáveis de Ambiente

O `.env` na raiz do projeto armazena credenciais (não versionado):

```
# Dev - seu token pessoal
DBT_DATABRICKS_TOKEN=seu_token_aqui
DBT_HTTP_PATH=sql/1.0/warehouses/xxxxx

# Prod - token da Service Principal
DBT_DATABRICKS_TOKEN_PROD=token_da_sp_aqui
```

Para usar no Git Bash:
```bash
source .env
dbt debug
```

### Como gerar o token da Service Principal

1. Databricks → **Admin Console** → **Service Principals**
2. Clique na SP (`1d6b3e3c-c04d-41e0-9883-ae8d467adcaf`)
3. **Secrets** → **Generate Secret**
4. Copie o token e cole no `.env` como `DBT_DATABRICKS_TOKEN_PROD`

---

## Comandos Úteis

```bash
dbt debug                             # testa conexão (dev)
dbt debug --target prod               # testa conexão (prod)
dbt run                               # roda todos os models (dev)
dbt run --target prod                 # roda todos os models (prod)
dbt run --select staging              # roda só staging
dbt run --select intermediate         # roda só intermediate
dbt test                              # roda todos os testes
dbt docs generate                     # gera documentação
dbt docs serve                        # abre documentação no browser
```
