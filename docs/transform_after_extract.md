# Orquestração Extração → Transformação

## Objetivo

Documentar o fluxo recomendado para executar as transformações dbt depois que os jobs de Bronze terminam. No estado atual do repositório, a extração e a transformação estão separadas: o Bitbucket Pipelines faz deploy e dispara os jobs de ingestão, enquanto o dbt é executado à parte.

## Visão Geral

O fluxo atual (via Orchestrator do Databricks) é:

1. `extract_lh_nautical` — 24 tabelas do SQL Server → Bronze
2. `extract_exchange_rates` — cotações PTAX → Bronze
3. `validate_extraction` — verifica se todas as tabelas foram carregadas
4. `apply_bronze_masks` — aplica column masking nas tabelas Bronze
5. `dbt deps` — instala dependências
6. `dbt run-operation create_mask_functions` — cria (idempotente) as funções de máscara
7. `dbt run --select intermediate` — materializa Silver; `int_customers`/`int_employees`/`int_suppliers` se auto-mascaram via post-hook ao serem criadas
8. `dbt test --select intermediate` — testa Silver
9. `dbt run --select marts` — materializa Gold; `dim_customers`/`dim_employees`/`dim_suppliers` se auto-mascaram via post-hook ao serem criadas
10. `dbt test --select marts` — testa Gold
11. `dbt run-operation apply_column_masks` — reaplica masking em Silver + Gold (segunda camada de garantia)

## Arquitetura

```mermaid
flowchart LR
  P[Bitbucket Pipelines] --> D[Databricks Bundle]
  D --> B[Bronze Jobs]
  B --> T[dbt Transformations]
  T --> M[Marts / Gold]
```

## Fluxo

1. Os jobs Bronze alimentam as tabelas Delta.
2. O dbt lê o Bronze via `profiles.yml` e `dbt_project.yml`.
3. A sequência recomendada é `staging`, depois `intermediate`, depois `marts`.
4. Por fim, os testes dbt confirmam se as regras de negócio continuam válidas.

## Componentes

- `bitbucket-pipelines.yml`: hoje faz deploy e executa apenas os jobs de extração.
- `databricks.yml`: define os recursos do bundle e os targets `dev`/`prod`.
- `profiles.yml`: autentica o dbt no Databricks.
- `dbt_project.yml`: define schemas e materializações.

## Dependências

- Catálogo Databricks acessível e autorizado.
- Variáveis de ambiente do dbt configuradas (`DBT_HTTP_PATH`, `DBT_DATABRICKS_TOKEN`, `DBT_DATABRICKS_TOKEN_PROD`).
- Dependências Python instaladas via `requirements.txt`.

## Configuração

Exemplo de execução local em sequência:

```bash
source .env
dbt debug
dbt run --select staging
dbt run --select intermediate
dbt run --select marts
dbt test
```

## Exemplos

Para validar apenas uma fatia do grafo:

```bash
dbt run --select stg_customers
dbt run --select int_customers
dbt run --select dim_customers
```

## Observações

- Não há automação de dbt no pipeline atual do repositório.
- Se a orquestração precisar ser automatizada, o ponto de extensão natural é o `bitbucket-pipelines.yml`.

## Referências

- [CI/CD](ci_cd_pipeline.md)
- [Configuração do dbt](dbt_configuration.md)
- [README principal](../README.md)