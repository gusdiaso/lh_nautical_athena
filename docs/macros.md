# Documentação das Macros dbt

## Visão Geral

As macros do dbt neste projeto ficam em `src/dbt/macros/` e concentram a lógica reutilizável do pipeline de transformação.

## Macros Existentes

### `generate_schema_name`

Arquivo: `src/dbt/macros/generate_schema_name.sql`

Evita que o dbt concatene o schema do profile com o schema customizado. O projeto usa diretamente o valor definido em `+schema` no `dbt_project.yml`.

### `sk_from_keys`

Arquivo: `src/dbt/macros/sk_from_keys.sql`

Gera surrogate keys com `md5(concat_ws('||', ...))` a partir de uma ou mais colunas.

### `clean_cep`

Arquivo: `src/dbt/macros/clean_cep.sql`

Remove caracteres não numéricos de CEPs e normaliza o valor para uso analítico.

### `apply_column_masks`

Arquivo: `src/dbt/macros/apply_column_masks.sql`

Executada via `dbt run-operation apply_column_masks` (step `apply_masks` no job `dbt_transform`). Aplica column masking nas tabelas Silver (`int_customers`, `int_employees`, `int_suppliers`) e Gold (`dim_customers`, `dim_employees`, `dim_suppliers`) usando as funções de máscara definidas no schema `gold`.

### `default_supplier_sku`

Arquivo: `src/dbt/macros/default_supplier_sku.sql`

Normaliza o `supplier_sku` aplicando `trim` e substituindo valores nulos ou placeholders (`'TBD'`, `'?'`, `'SEM-CODIGO'`, `''`) por um identificador no formato `SUP-{supplier_id}-{product_variant_id}`. Usada na `int_product_suppliers` e nas fatos de compra e recebimento.

## Dependências

- `packages.yml` declara `dbt-labs/dbt_utils`.
- `dbt_project.yml` define os schemas e materializações que as macros suportam.

## Como Validar

```bash
source .env
dbt compile --select staging
dbt compile --select intermediate
dbt compile --select marts
```

## Observações

- As cinco macros do projeto estão documentadas neste arquivo e em `src/dbt/macros/macros.yml`.
- A documentação antiga de macros futuras foi removida para manter o guia alinhado ao código atual.

## Referências

- [Configuração do dbt](dbt_configuration.md)
- [Camada Staging](staging.md)
- [Camada Intermediate](intermediate.md)
- [README do projeto](../README.md)