# Documentação das Macros dbt

## Visão Geral

As **macros** no dbt são funções reutilizáveis escritas em Jinja + SQL que permitem automatizar tarefas repetitivas, padronizar código e criar abstrações poderosas.

Neste projeto, as macros ficam em: `src/dbt/macros/`

---

## Macros Existentes

### 1. `generate_schema_name` — Controle do Schema

**Arquivo:** `src/dbt/macros/generate_schema_name.sql`

```sql
{% macro generate_schema_name(custom_schema_name, node) -%}

    {%- if custom_schema_name is none -%}

        {{ target.schema }}

    {%- else -%}

        {{ custom_schema_name | trim }}

    {%- endif -%}

{%- endmacro %}
```

#### O que faz

Intercepta a resolução do schema pelo dbt. Por padrão, o dbt **concatena** o schema do profile + o schema customizado (ex: `silver_silver`). Esta macro faz o dbt usar **apenas** o valor definido em `+schema` no `dbt_project.yml`.

#### Por que existe

Sem esta macro:
```
profiles.yml: schema: silver
dbt_project.yml: +schema: silver
Resultado: dev_lh_nautical.silver_silver.stg_customers  ← ERRADO
```

Com esta macro:
```
Resultado: dev_lh_nautical.silver.stg_customers  ← CORRETO
```

#### Parâmetros

| Parâmetro | Tipo | Descrição |
|-----------|------|-----------|
| `custom_schema_name` | string | Valor do `+schema` no `dbt_project.yml` (ou `none`) |
| `node` | objeto | Metadados do model (nome, path, tags, etc.) |

#### Como testar

```bash
# Compilar um model para ver o schema resolvido
dbt compile --select stg_customers

# Verificar no target/compiled/
cat target/compiled/lh_nautical/staging/stg_customers.sql
```

---

## Macros Recomendadas (Para Criar)

As macros abaixo **não existem ainda** mas são altamente recomendadas para este projeto. Crie conforme a necessidade.

---

### 2. `generate_surrogate_key` — Chave Substituta (Hash)

**Arquivo sugerido:** `src/dbt/macros/generate_surrogate_key.sql`

```sql
{% macro generate_surrogate_key(columns) -%}
    {%- set cols = columns if columns is iterable and columns is not string else [columns] -%}
    {%- set hash_cols = [] -%}
    {%- for col in cols -%}
        {%- do hash_cols.append("coalesce(cast(" ~ col ~ " as string), '')") -%}
    {%- endfor -%}
    md5(concat({{ hash_cols | join(", ") }}))
{%- endmacro %}
```

#### Uso

```sql
-- Em dim_customers.sql
SELECT
    {{ generate_surrogate_key(['nk_customer_id']) }} as sk_customer
    , nk_customer_id
    , ...
FROM {{ ref('int_customers') }}
```

#### Vantagens

- Determinístico: mesmo input = mesmo hash
- Funciona com múltiplas colunas (chaves compostas)
- Compatível com qualquer warehouse (usa MD5 padrão)

---

### 3. `standardize_column_names` — Padronização de Nomes

**Arquivo sugerido:** `src/dbt/macros/standardize_column_names.sql`

```sql
{% macro standardize_column_names(columns, prefix='') -%}
    {%- set standardized = [] -%}
    {%- for col in columns -%}
        {%- set clean_col = col
            | lower
            | replace(' ', '_')
            | replace('-', '_')
            | replace('.', '_')
            | replace('/', '_')
            | replace('(', '')
            | replace(')', '')
            | trim -%}
        {%- do standardized.append(prefix ~ clean_col) -%}
    {%- endfor -%}
    {{ standardized | join(', ') }}
{%- endmacro %}
```

#### Uso no Staging

```sql
-- stg_customers.sql
WITH source AS (
    SELECT * FROM {{ source('bronze', 'customers') }}
)
SELECT
    {{ standardize_column_names(adapter.get_columns_in_relation(source), 'c_') }}
FROM source
```

---

### 4. `get_incremental_filter` — Filtro Incremental Padrão

**Arquivo sugerido:** `src/dbt/macros/get_incremental_filter.sql`

```sql
{% macro get_incremental_filter(date_column, lookback_days=1) -%}
    {%- if is_incremental() -%}
        WHERE {{ date_column }} >= (
            SELECT date_sub(max({{ date_column }}), {{ lookback_days }})
            FROM {{ this }}
        )
    {%- endif -%}
{%- endmacro %}
```

#### Uso

```sql
-- int_orders.sql (incremental)
SELECT * FROM {{ ref('stg_orders') }}
{{ get_incremental_filter('placed_at', 7) }}
```

---

### 5. `test_no_duplicates` — Teste de Duplicatas Reutilizável

**Arquivo sugerido:** `src/dbt/macros/test_no_duplicates.sql`

```sql
{% macro test_no_duplicates(model, column_name) -%}
    SELECT {{ column_name }}, COUNT(*) as cnt
    FROM {{ model }}
    GROUP BY {{ column_name }}
    HAVING COUNT(*) > 1
{%- endmacro %}
```

#### Uso no schema.yml

```yaml
tests:
  - test_no_duplicates:
      column_name: customer_id
```

---

### 6. `exchange_rate_lookup` — Lookup de Câmbio (Regra de Negócio)

**Arquivo sugerido:** `src/dbt/macros/exchange_rate_lookup.sql`

```sql
{% macro exchange_rate_lookup(date_col, currency_col, rate_type='sell') -%}
    CASE
        WHEN {{ currency_col }} = 'BRL' THEN 1.0
        ELSE COALESCE((
            SELECT {{ rate_type ~ '_rate' }}
            FROM {{ ref('int_exchange_rates') }} er
            WHERE er.currency = {{ currency_col }}
              AND er.rate_date = DATE({{ date_col }})
            ORDER BY er.rate_date DESC
            LIMIT 1
        ), (
            SELECT {{ rate_type ~ '_rate' }}
            FROM {{ ref('int_exchange_rates') }} er
            WHERE er.currency = {{ currency_col }}
              AND er.rate_date < DATE({{ date_col }})
            ORDER BY er.rate_date DESC
            LIMIT 1
        ), 1.0)
    END
{%- endmacro %}
```

#### Uso

```sql
-- int_purchase_order_items.sql
SELECT
    poi.*
    , poi.unit_cost * {{ exchange_rate_lookup('po_date', 'currency') }} as unit_cost_brl
FROM {{ ref('stg_purchase_order_items') }} poi
```

---

### 7. `audit_columns` — Colunas de Auditoria Padrão

**Arquivo sugerido:** `src/dbt/macros/audit_columns.sql`

```sql
{% macro audit_columns() -%}
    CURRENT_TIMESTAMP() AS _dbt_created_at
    , CURRENT_TIMESTAMP() AS _dbt_updated_at
    , '{{ invocation_id }}' AS _dbt_invocation_id
    , '{{ model.name }}' AS _dbt_model_name
{%- endmacro %}
```

#### Uso

```sql
-- Qualquer model
SELECT
    *
    , {{ audit_columns() }}
FROM {{ ref('int_customers') }}
```

---

## Como Criar uma Nova Macro

### Passo a Passo

1. **Crie o arquivo** em `src/dbt/macros/nome_da_macro.sql`

2. **Escreva a macro** seguindo o padrão:

```sql
{% macro nome_da_macro(parametro1, parametro2='default') -%}
    
    -- Lógica Jinja/SQL aqui
    {{ parametro1 }} AS coluna_exemplo

{%- endmacro %}
```

3. **Teste compilando** um model que use a macro:

```bash
dbt compile --select meu_model
```

4. **Verifique o SQL gerado** em `target/compiled/...`

### Boas Práticas

| Prática | Por quê |
|---------|---------|
| Use `{% -%}` e `{%- %}` | Remove whitespace extra no SQL gerado |
| Documente com comentários `--` | Ajuda quem lê o código da macro |
| Teste com `dbt compile` | Vê o SQL final sem rodar no warehouse |
| Use `adapter.get_columns_in_relation()` | Para macros que inspecionam schemas |
| Prefixe macros privadas com `_` | Ex: `_internal_helper` |

---

## Debugging de Macros

### Ver SQL Gerado

```bash
# Compila e mostra no terminal
dbt compile --select stg_customers --inline

# Ou veja o arquivo
cat target/compiled/lh_nautical/staging/stg_customers.sql
```

### Log de Variáveis Jinja

```sql
{% macro debug_macro(var) -%}
    {% do log("DEBUG: var = " ~ var, info=true) %}
    {{ var }}
{%- endmacro %}
```

### Erros Comuns

| Erro | Causa | Solução |
|------|-------|---------|
| `macro not found` | Arquivo fora de `macro-paths` | Verifique `dbt_project.yml` |
| `Unexpected end of template` | Falta `{% endmacro %}` | Feche todos os blocos |
| `Undefined variable` | Variável Jinja não existe | Use `{% if var is defined %}` |
| SQL inválido gerado | Lógica Jinja errada | Use `dbt compile` para ver o SQL |

---

## Referência Rápida: Variáveis dbt Disponíveis nas Macros

| Variável | Descrição |
|----------|-----------|
| `target` | Config do target ativo (database, schema, host, etc.) |
| `model` | Metadados do model atual (name, schema, database, tags) |
| `source` | Metadados da source (se em context de source) |
| `ref` | Função para referenciar outros models |
| `source` | Função para referenciar sources |
| `var()` | Acessa variáveis do `dbt_project.yml` ou CLI |
| `env_var()` | Acessa variáveis de ambiente |
| `adapter` | Adapter do warehouse (methods: `get_columns_in_relation`, etc.) |
| `run_started_at` | Timestamp de início da execução |
| `invocation_id` | ID único da execução do dbt |
| `this` | Relação (table/view) do model atual |
| `flags` | Flags de execução (FULL_REFRESH, etc.) |

---

## Macros do Pacote `dbt-utils` (Já Disponíveis)

Se adicionar `dbt-utils` no `packages.yml`, ganha macros prontas:

```yaml
# packages.yml
packages:
  - package: dbt-labs/dbt_utils
    version: 1.1.1
```

```bash
dbt deps
```

### Macros Úteis do dbt-utils

| Macro | Uso |
|-------|-----|
| `surrogate_key([col1, col2])` | Gera hash MD5 de chaves |
| `star(from=ref('model'), except=[col1])` | SELECT * exceto colunas |
| `pivot(column, values, then_value)` | Pivot dinâmico |
| `datediff(date1, date2, unit)` | Diferença de datas cross-DB |
| `dateadd(unit, amount, date)` | Adiciona intervalo cross-DB |
| `get_columns_in_relation(relation)` | Lista colunas de uma relation |
| `escape_html(text)` | Escapa HTML |

