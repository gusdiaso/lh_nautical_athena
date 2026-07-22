# Estratégia de Testes da Camada Marts

## Objetivo

Documentar como a camada Marts do projeto LH Nautical é protegida por testes genéricos e singulares.

## Visão Geral

A camada `marts` possui 12 models materializados como `table` no schema `gold`, conforme `dbt_project.yml`.

A validação atual está distribuída em dois níveis:

- testes genéricos declarados nos arquivos `src/dbt/models/marts/*.yml`
- testes singulares em `src/dbt/tests/*.sql`

## Cobertura Atual

- Models marts: 12
- Testes singulares: 36
- Unit tests: 0

Os testes genéricos cobrem chaves, nulidade, valores aceitos e relacionamentos. Como os contratos ficam ao lado de cada model, não existe um arquivo consolidado `marts.yml` no repositório.

## Padrões de Validação

- Dimensões usam `not_null` e `unique` nas chaves críticas.
- Fatos usam `relationships` para dimensões conformadas.
- Flags booleanas usam `accepted_values` com `[true, false]`.
- Regras de negócio mais específicas ficam nos testes singulares.

## Exemplos de Regras Protegidas

- `dim_date` valida unicidade do grão diário e domínios de calendário.
- `dim_customers` e `dim_employees` validam chaves, campos obrigatórios e flags booleanas.
- `fact_order_items`, `fact_purchase_order_items` e `fact_goods_receipt_items` validam relacionamentos e métricas de linha.
- `fact_payments`, `fact_stock_movements` e `fact_return_items` validam status, direção e consistência de valores.

## Arquivos de Apoio

- `src/dbt/models/marts/*.sql`: implementação dos models.
- `src/dbt/models/marts/*.yml`: testes genéricos e descrições das colunas.
- `src/dbt/tests/*.sql`: testes singulares de regra de negócio.

## Como Validar

```bash
source .env
dbt test --select marts
```

Se for necessário validar só uma fatia do grafo:

```bash
dbt test --select dim_customers
dbt test --select fact_order_items
```

## Observações

- O arquivo antigo que centralizava os testes da camada não existe mais; a validação está dispersa pelos YAMLs de cada model.
- A contagem de 36 testes singulares reflete os arquivos `.sql` presentes em `src/dbt/tests/`.

## Referências

- [Camada Marts](marts.md)
- [Star Schema](star_schema.md)
- [README do projeto](../README.md)