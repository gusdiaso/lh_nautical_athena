# Documentacao: extract_exchange_rates

## Visao Geral

Pipeline que extrai cotacoes de moedas (PTAX) do Banco Central do Brasil para a camada **Bronze** no Databricks.

**Fonte:** API PTAX do Banco Central
**Modo de carga:** Incremental (apenas novos registros)

## Fluxo dos Dados

```
Banco Central (API PTAX)
       │
       ▼ ─── HTTP (requisicoes REST)
┌─────────────────────────┐
│    Bronze (Delta Lake)  │  ← extract_exchange_rates.py
└─────────────────────────┘
```

## Arquitetura dos Arquivos

```
src/ingestion/
├── config.py                  # Constantes e configuracoes
├── utils.py                   # Funcoes reutilizaveis (Spark, Delta)
├── extract_lh_nautical.py     # Extracao SQL Server → Bronze
└── extract_exchange_rates.py  # Extracao API BCB → Bronze

resources/extract/
└── extract_exchange_rates.yml # Configuracao do job (DAB)

docs/
└── extract_exchange_rates.md  # Esta documentacao
```

| Arquivo                     | Funcao                                     |
| --------------------------- | ------------------------------------------ |
| `config.py`                 | URL JDBC, lista de tabelas, schemas        |
| `utils.py`                  | Funcoes compartilhadas (Spark, Delta Lake) |
| `extract_exchange_rates.py` | Logica de extracao da API PTAX             |
| `extract_exchange_rates.yml`| Configuracao do job no Databricks          |

> **Nota:** A configuracao completa do job (DAB) esta em `docs/dab_configuration.md`.

---

## Funcoes Compartilhadas (utils.py)

| Funcao                                  | Descricao                                         |
| --------------------------------------- | ------------------------------------------------- |
| `build_spark_session()`                 | Cria sessao Spark (Databricks Runtime ou externa) |
| `get_dbutils()`                         | Retorna dbutils para acesso a segredos            |
| `save_full(spark, df, table)`           | Salva DataFrame sobrescrevendo a tabela (full)    |
| `save_append(spark, df, table)`         | Acrescenta linhas a tabela existente (append)     |
| `create_schema(spark, catalog, schema)` | Cria schema se nao existir                        |
| `table_exists(spark, table)`            | Verifica se tabela existe                         |

## Como Executar

```bash
# Validar o bundle
databricks bundle validate

# Deploy para dev
databricks bundle deploy --target dev

# Executar o job
databricks bundle run extract_exchange_rates --target dev

# Executar com load-mode full (reprocessar tudo)
databricks bundle run extract_exchange_rates --target dev -- --load-mode full
```

## Moedas Rastreadas

| Codigo | Moeda            |
| ------ | ---------------- |
| `USD`  | Dolar Americano  |
| `EUR`  | Euro             |

## Metadados Adicionados

| Coluna          | Descricao                                    |
| --------------- | -------------------------------------------- |
| `_ingested_at`  | Timestamp da ingestao                        |
| `_source_path`  | Origem dos dados (api://bcb/ptax/...)        |

## Estrutura do Codigo

### Funcoes Principais

| Funcao                      | O que faz                                      |
| --------------------------- | ---------------------------------------------- |
| `parse_args()`              | Le argumentos da linha de comando               |
| `fetch_ptax_day()`          | Busca cotacao de 1 dia via API                  |
| `collect_ptax_daily()`      | Coleta cotacoes de um periodo                   |
| `get_currency_start_date()` | Busca data inicial incremental                  |
| `merge_exchange_rates()`    | Merge/upsert na tabela Delta                    |
| `main()`                    | Entry point do script                           |

### Fluxo de Execucao

```
main()
  │
  ├── build_spark_session()        → cria sessao Spark
  ├── create_schema()              → cria schema Bronze
  │
  └── para cada moeda (USD, EUR):
        │
        ├── get_currency_start_date()  → busca checkpoint
        ├── collect_ptax_daily()       → busca dados da API
        │     └── fetch_ptax_day()     → busca 1 dia
        │
        └── merge_exchange_rates()     → salva no Bronze
```

## Troubleshooting

| Problema               | Causa                       | Solucao                        |
| ---------------------- | --------------------------- | ------------------------------ |
| `Connection timeout`   | API do BCB indisponivel     | Retry automatico ou aguardar   |
| `Empty DataFrame`      | Nenhum dado para a data     | Verificar intervalo de datas   |
| `Schema not found`     | Schema Bronze nao existe    | Script cria automaticamente    |
| `Duplicate rows`       | Execucao repetida           | Usar modo incremental          |
