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
├── extract_lh_nautical.yml    # Configuracao do job (DAB) - GERADO
├── extract_exchange_rates.yml # Configuracao do job exchange rates
└── generate_dab_lh_nautical.py           # Script gerador do YAML

docs/
└── extract_lh_nautical.md     # Esta documentacao
```

| Arquivo                       | Funcao                                     |
| ----------------------------- | ------------------------------------------ |
| `config.py`                   | URL JDBC, lista de tabelas, schemas        |
| `utils.py`                    | Funcoes compartilhadas (Spark, Delta Lake) |
| `extract_lh_nautical.py`      | Logica de extracao do SQL Server           |
| `extract_lh_nautical.yml`     | Configuracao do job no Databricks (gerado) |
| `generate_dab_lh_nautical.py` | Script gerador do YAML                     |

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

## Gerar YAML Automaticamente

### Por que foi feito?

O arquivo `extract_lh_nautical.yml` original tinha **24 tasks quase idênticas** - cada uma usando o mesmo script, diferindo apenas pelo nome da tabela. Isso viola o princípio **DRY** (Don't Repeat Yourself) e dificulta a manutenção.

**Problema:** Para adicionar uma tabela, era necessário copiar e colar 12 linhas de YAML e alterar 2 valores. Com 24 tabelas, isso significava ~300 linhas repetitivas.

**Solução:** Um script Python (`generate_dab_lh_nautical.py`) gera o YAML automaticamente a partir da lista de tabelas definida em `config.py`.

### Como usar

```bash
# 1. Adicione a tabela em src/ingestion/config.py
TABLES = [
    ...
    "nova_tabela",  # ← adicione aqui
]

# 2. Regenere o YAML
python resources/extract/generate_dab_lh_nautical.py

# 3. Valide o bundle
databricks bundle validate
```

### Fluxo

```
config.py (TABLES)
       │
       ▼
generate_dab_lh_nautical.py
       │
       ▼
extract_lh_nautical.yml
```

> **Importante:** Nunca edite o YAML manualmente. Altere apenas `config.py` e execute `generate_dab_lh_nautical.py`.

## Lista de Tabelas

| Categoria    | Tabelas                                                                    | Modelo dbt |
| ------------ | -------------------------------------------------------------------------- | ---------- |
| Referencia   | categories, brands, locations, attributes, employees                       | ✅ Sim     |
| Clientes     | customers, addresses                                                       | ✅ Sim     |
| Fornecedores | suppliers                                                                  | ✅ Sim     |
| Produtos     | products, product_variants, variant_attribute_values, product_suppliers    | ✅ Sim     |
| Compras      | purchase_orders, purchase_order_items, goods_receipts, goods_receipt_items | ✅ Sim     |
| Vendas       | orders, order_items, payments, **fiscal_invoices**                         | ⚠️ fiscal_invoices não possui modelo dbt |
| Devolucoes   | returns, return_items                                                      | ✅ Sim     |
| Estoque      | stock_levels, stock_movements                                              | ✅ Sim     |

## Retry Automatico

O pipeline utiliza a biblioteca `tenacity` para retry automatico em caso de falhas de conexao com o SQL Server.

| Parametro      | Valor                    | Descricao                         |
| -------------- | ------------------------ | --------------------------------- |
| `stop`         | 3 tentativas             | Para apos 3 falhas consecutivas   |
| `wait`         | Exponencial (2s, 4s, 8s) | Espera crescente entre tentativas |
| `retry`        | `Exception`              | Retry em qualquer excecao         |
| `before_sleep` | Log no console           | Exibe mensagem de tentativa       |

**Fluxo de retry:**

```
Tentativa 1 → Falha → Espera 2s
Tentativa 2 → Falha → Espera 4s
Tentativa 3 → Falha → Levanta excecao
```

---

## Dependencias

Para executar localmente, instale as dependencias:

```bash
pip install -r requirements.txt
```

| Dependencia          | Versao      | Uso                           |
| -------------------- | ----------- | ----------------------------- |
| `pyspark`            | —           | Sessao Spark (fornecido pelo Databricks Runtime) |
| `delta-spark`        | —           | Formato Delta Lake (fornecido pelo Databricks Runtime) |
| `tenacity`           | >=8.2,<10.0 | Retry automatico              |

---

## Metadados Adicionados

| Coluna         | Descricao                                        |
| -------------- | ------------------------------------------------ |
| `_ingested_at` | Timestamp da ingestao                            |
| `_source_path` | Origem dos dados (ex: sqlserver://dbo.customers) |

## Estrutura do Codigo

### Funcoes Principais (extract_lh_nautical.py)

| Funcao                  | O que faz                            |
| ----------------------- | ------------------------------------ |
| `parse_args()`          | Le argumentos da linha de comando    |
| `select_tables(name)`   | Filtra tabela ou retorna todas       |
| `read_source_data(...)` | Le dados do SQL Server via JDBC      |
| `extract_table(...)`    | Extrai 1 tabela completa (com retry) |
| `run_extraction(...)`   | Processa todas as tabelas            |
| `main()`                | Entry point do script                |

### Funcoes Compartilhadas (utils.py)

| Funcao                  | O que faz                         |
| ----------------------- | --------------------------------- |
| `build_spark_session()` | Cria sessao Spark                 |
| `get_dbutils()`         | Acessa segredos do Databricks     |
| `save_full(...)`        | Salva DataFrame como tabela Delta |
| `create_schema(...)`    | Cria schema se nao existir        |

### Fluxo de Execucao

```
main()
  │
  ├── parse_args()              → le argumentos CLI
  ├── build_spark_session()     → cria sessao Spark (utils.py)
  ├── get_dbutils()             → acessa segredos (utils.py)
  ├── create_schema()           → cria schema Bronze (utils.py)
  ├── select_tables()           → seleciona tabelas
  │
  └── run_extraction()          → para cada tabela:
        │
        └── extract_table()     → com retry (tenacity)
              ├── read_source_data()   → le do SQL Server
              ├── withColumn()         → adiciona metadados
              └── save_full()          → salva no Bronze (utils.py)
```

## Troubleshooting

| Problema             | Causa                    | Solucao                           |
| -------------------- | ------------------------ | --------------------------------- |
| `Connection refused` | SQL Server indisponivel  | Verificar IP/porta no `config.py` |
| `Connection timeout` | Firewall ou rede         | Verificar regras de rede          |
| `Schema not found`   | Schema Bronze nao existe | Script cria automaticamente       |
| `Table not found`    | Tabela nao existe no SQL | Verificar lista TABLES em config  |
| `Permission denied`  | Credenciais invalidas    | Verificar Databricks Secrets      |
| `Retry failed`       | 3 tentativas sem sucesso | Verificar conectividade/rede      |
