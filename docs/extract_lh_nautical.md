# Documentacao: extract_lh_nautical

## Visao Geral

Pipeline que extrai 24 tabelas do SQL Server (lh_nautical) para a camada **Bronze** no Databricks.

**Modo de carga:** Full (sobrescreve a tabela inteira a cada execucao).

## Fluxo dos Dados

```
SQL Server (ERP)
       │
       ▼ ─── JDBC (leitura completa)
┌─────────────────────────┐
│    Bronze (Delta Lake)  │  ← extract_lh_nautical.py
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
└── extract_lh_nautical.yml    # Configuracao do job (DAB)

docs/
└── extract_lh_nautical.md     # Esta documentacao
```

| Arquivo                     | Funcao                                     |
| --------------------------- | ------------------------------------------ |
| `config.py`                 | URL JDBC, lista de tabelas, schemas        |
| `utils.py`                  | Funcoes compartilhadas (Spark, Delta Lake) |
| `extract_lh_nautical.py`    | Logica de extracao do SQL Server           |
| `extract_lh_nautical.yml`   | Configuracao do job no Databricks          |

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

# Executar todas as tabelas
databricks bundle run extract_lh_nautical --target dev

# Executar uma tabela especifica
databricks bundle run extract_lh_nautical --target dev -- --table customers
```

## Lista de Tabelas

| Categoria    | Tabelas                                                                    |
| ------------ | -------------------------------------------------------------------------- |
| Referencia   | categories, brands, locations, attributes, employees                       |
| Clientes     | customers, addresses                                                       |
| Fornecedores | suppliers                                                                  |
| Produtos     | products, product_variants, variant_attribute_values, product_suppliers    |
| Compras      | purchase_orders, purchase_order_items, goods_receipts, goods_receipt_items |
| Vendas       | orders, order_items, payments, fiscal_invoices                             |
| Devolucoes   | returns, return_items                                                      |
| Estoque      | stock_levels, stock_movements                                              |

## Metadados Adicionados

| Coluna         | Descricao                                        |
| -------------- | ------------------------------------------------ |
| `_ingested_at` | Timestamp da ingestao                            |
| `_source_path` | Origem dos dados (ex: sqlserver://dbo.customers) |

## Estrutura do Codigo

### Funcoes Principais

| Funcao                  | O que faz                         |
| ----------------------- | --------------------------------- |
| `parse_args()`          | Le argumentos da linha de comando |
| `build_spark_session()` | Cria sessao Spark                 |
| `get_dbutils()`         | Acessa segredos do Databricks     |
| `select_tables(name)`   | Filtra tabela ou retorna todas    |
| `read_source_data(...)` | Le dados do SQL Server via JDBC   |
| `save_full(...)`        | Salva DataFrame como tabela Delta |
| `extract_table(...)`    | Extrai 1 tabela completa          |
| `run_extraction(...)`   | Processa todas as tabelas         |
| `main()`                | Entry point do script             |

### Fluxo de Execucao

```
main()
  │
  ├── build_spark_session()     → cria sessao Spark
  ├── get_dbutils()             → acessa segredos
  ├── select_tables()           → seleciona tabelas
  │
  └── run_extraction()          → para cada tabela:
        │
        └── extract_table()
              ├── read_source_data()   → le do SQL Server
              ├── withColumn()         → adiciona metadados
              └── save_full()          → salva no Bronze
```

## Troubleshooting

| Problema             | Causa                     | Solucao                           |
| -------------------- | ------------------------- | --------------------------------- |
| `Connection refused` | SQL Server indisponivel   | Verificar IP/porta no `config.py` |
| `Schema not found`   | Schema Bronze nao existe  | Script cria automaticamente       |
| `Table not found`    | Tabela ainda nao extraida | Rodar o pipeline completo         |
| `Permission denied`  | Credenciais invalidas     | Verificar Databricks Secrets      |
