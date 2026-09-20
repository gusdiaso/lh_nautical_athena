# LH Nautical — Documento Oficial do Projeto

## 1. Cenário anterior e problemas enfrentados

Antes da implementação deste pipeline, a LH Nautical operava com dados dispersos em um **ERP SQL Server on-premise** sem qualquer camada de tratamento analítico. As áreas de negócio enfrentavam desafios críticos:

| Problema | Impacto |
|----------|---------|
| **Dados brutos sem padronização** | Cada consulta exigia conhecimento profundo do banco operacional, com nomes de colunas confusos e tipos inconsistentes |
| **Ausência de histórico confiável** | Impossibilidade de comparar períodos sem reprocessar dados manualmente |
| **Sem rastreabilidade** | Não era possível identificar de onde os dados vinham nem quando foram extraídos |
| **Dados sensíveis expostos** | CPF, CNPJ, e-mail e telefone eram acessíveis a qualquer pessoa com acesso ao banco |
| **Processos manuais e frágeis** | Extrações ad-hoc sem controle de versão, sem retry em falhas, sem orquestração |
| **Sem testes de qualidade** | Erros nos dados eram descobertos tarde demais, já em relatórios finais |
| **Curva lenta para novos membros** | Sem documentação, sem dicionário de dados — cada novo integrante precisava decifrar o banco sozinho |

## 2. Solução implementada

Foi construído um **pipeline de dados corporativo completo** no ecossistema **Databricks**, seguindo a **Arquitetura Medalhão** (Bronze → Silver → Gold). Os dados operacionais do ERP SQL Server (24 tabelas) e as cotações de moedas USD/EUR da **API PTAX do Banco Central** são extraídos automaticamente, transformados com **dbt**, e disponibilizados como um **modelo dimensional (Star Schema)** no **Unity Catalog** com **Delta Lake**.

### O que a solução entrega:

- **Automação total** — ingestão, transformação e validação executadas diariamente sem intervenção manual
- **Dados confiáveis** — 30+ testes de qualidade garantem integridade antes de chegar às análises
- **Documentação viva** — dicionário de dados, diagrama do schema, linhagem e metadados gerados automaticamente
- **Segurança por design** — dados sensíveis mascarados em query time para usuários não autorizados
- **Resiliência** — retry automático com backoff exponencial em todas as extrações
- **Rastreabilidade** — metadados `_ingested_at` e `_source_path` em toda tabela Bronze
- **Notificações em tempo real** — falhas de jobs são alertadas no Slack e por e-mail
- **CI/CD integrado** — deploy automático em produção via Bitbucket Pipelines

## 3. Perguntas de negócio que queremos responder

O modelo dimensional foi desenhado para responder a três pilares estratégicos:

### 3.1 Saúde financeira

| Pergunta | Como o modelo responde |
|----------|----------------------|
| Qual é o faturamento líquido por canal, loja e período? | `fact_order_items` com `net_line_total` + `dim_locations` + `dim_date` |
| Quais produtos têm margem bruta negativa ou abaixo da meta? | `dim_products` com `gross_margin_percentage` + `fact_order_items` |
| Qual é o custo estimado das mercadorias vendidas (CPV)? | `fact_order_items` com `estimated_cost_of_goods_sold` |
| Como estão os pagamentos? Qual o valor recebido vs. pendente? | `fact_payments` com `paid_amount`, `payment_status` |
| Qual o impacto cambial nas compras internacionais? | `fact_purchase_order_items` com `exchange_rate_sell` e valores em BRL |
| Qual a inadimplência por cliente e região? | `fact_payments` + `dim_customers` + `dim_locations` |

### 3.2 Logística e ruptura de estoque

| Pergunta | Como o modelo responde |
|----------|----------------------|
| Quais produtos estão com estoque abaixo do nível crítico? | `fact_stock_movements` + `dim_products` + análise de saldo |
| Onde estão os gargalos de recebimento de mercadorias? | `fact_goods_receipt_items` com `is_late_receipt`, `delivery_variance_days` |
| Quais fornecedores atrasam entregas com mais frequência? | `fact_goods_receipt_items` + `dim_suppliers` |
| Qual a diferença entre o que foi comprado e o que foi recebido? | `fact_purchase_order_items` vs. `fact_goods_receipt_items` (quantidades) |
| Há produtos parados em estoque sem movimentação? | `fact_stock_movements` com `movement_type` e data da última movimentação |

### 3.3 Retenção de clientes e abandono

| Pergunta | Como o modelo responde |
|----------|----------------------|
| Quais clientes solicitaram reembolso em vez de troca? | `fact_return_items` com `is_refund`, `is_exchange`, `return_reason_group` |
| Quais produtos têm maior taxa de devolução? | `fact_return_items` + `dim_products` (taxa de retorno por SKU) |
| Qual o motivo mais frequente das devoluções? | `fact_return_items` com `reason_normalized`, `return_reason_group` |
| Clientes que devolvem voltam a comprar? | `fact_return_items` + `fact_order_items` (análise de recorrência) |
| Qual o impacto financeiro das devoluções? | `fact_return_items` com `total_line_refund_amount` |
| Há clientes que abandonam a compra em vez de solicitar troca? | `fact_return_items` + `dim_customers` (comportamento por perfil) |

## 4. Justificativas das decisões técnicas

### 4.1 Arquitetura em camadas (Staging → Intermediate → Marts)

Optamos por **três camadas de transformação** no dbt para separar responsabilidades e garantir rastreabilidade:

| Camada | Materialização | Por quê |
|--------|---------------|---------|
| **Staging** | `ephemeral` (CTE) | Apenas renomeia colunas e tipa dados — não ocupa armazenamento, é injetada como CTE nos modelos seguintes |
| **Intermediate** | `table` (schema `silver`) | Concentra toda a lógica de limpeza, dedup, correção e enriquecimento. Materializada para debug e rastreabilidade. Se algo falha, sabemos exatamente em qual tabela |
| **Marts** | `table` (schema `gold`) | Modelo dimensional final, pronto para BI. Separado do intermediate para que consumidores não dependam de lógica de limpeza |

**Benefício:** Se um erro de qualidade é identificado, a correção é feita no intermediate sem impactar a estrutura do gold. Se um novo campo é necessário no BI, adiciona-se no marts sem refatorar a limpeza.

### 4.2 Privacidade e princípio do privilégio mínimo (LGPD)

Em conformidade com a **Lei Geral de Proteção de Dados (LGPD)**, implementamos **Column Masking** no Unity Catalog. As funções de máscara são aplicadas em query time:

- `mask_full` — oculta completamente (`***MASKED***`)
- `mask_cpf` — oculta completamente (`***MASKED***`)
- `mask_email` — oculta completamente (`***MASKED***`)
- `mask_phone` — oculta completamente (`***MASKED***`)

**Regra:** Apenas membros do grupo `lh_nautical_dev` enxergam valores reais — o grupo verificado é fixo, independente do catálogo (`dev` ou `prod`). Qualquer outro usuário, incluindo membros de `lh_nautical_prod`, vê apenas dados mascarados. Isso vale para **Bronze, Silver e Gold**, em ambos os catálogos, garantindo proteção em todas as camadas.

### 4.3 Documentação robusta para onboarding acelerado

O projeto conta com **documentação viva e versionada**:

| Documento | Finalidade |
|-----------|-----------|
| `docs/dictionary.md` | Dicionário de dados completo com todas as 25 tabelas (24 ERP + exchange_rates), colunas, tipos e relacionamentos |
| `docs/star_schema.md` | Modelo dimensional com descrição de cada dimensão e fato |
| `docs/macros.md` | Documentação de todas as macros dbt com parâmetros e exemplos |
| `docs/dbt_configuration.md` | Guia de configuração do dbt + profiles |
| `docs/ci_cd_pipeline.md` | Documentação do pipeline de CI/CD |
| `docs/extract_lh_nautical.md` | Detalhes da extração SQL Server |
| `docs/extract_exchange_rates.md` | Detalhes da extração da API BCB |
| `dbt docs generate` | Documentação interativa com linhagem, testes e descrições |

**Resultado:** Novos membros do time conseguem entender o fluxo completo, o significado de cada coluna e como contribuir em dias, não em semanas.

### 4.4 Notificações e comunicação

| Evento | Canal | Destinatário |
|--------|-------|-------------|
| Falha em job de produção | Slack | `lh-team-athena` |
| Falha em job de produção | E-mail | Tech lead (`gustavo.dias@indicium.ai`) |
| Commit em qualquer branch | Slack | `lh-team-athena` |
| Abertura de PR | Slack | `lh-team-athena` |
| Merge na `main` | Slack | `lh-team-athena` |

### 4.5 Fluxo de desenvolvimento

Adotamos um fluxo baseado em **branches e revisão coletiva** para garantir qualidade e envolvimento de todo o time:

```
feature/ → develop (PR revisado por todo o time) → main (merge apenas após aprovação)
```

- Todo desenvolvimento ocorre em branches a partir da `develop`
- **Pull Requests obrigatoriamente revisados por todo o time** — garante qualidade e envolvimento coletivo
- A branch `main` só recebe merge a partir da `develop`, garantindo que código quebrado nunca chegue ao ambiente de produção
- Commits e PRs são automaticamente notificados no Slack do time

### 4.6 Padrão leading comma no SQL

Adotamos a convenção **leading comma** para formatação de consultas SQL:

```sql
SELECT
    coluna_um
    , coluna_dois
    , coluna_tres
FROM tabela
```

**Por quê?**
- Facilita inclusão/remoção de colunas sem alterar linhas anteriores
- O diff do Git fica mais limpo — uma nova coluna adiciona apenas uma linha
- Consistência em todo o código do projeto

## 5. Fluxo de dados

### 5.1 Etapas do pipeline

O pipeline completo é executado diariamente de forma automatizada. Cada etapa tem responsabilidade clara:

**Etapa 1 — Ingestão (Bronze)**

Duas extrações acontecem em paralelo:

1. **SQL Server → Bronze:** 24 tabelas operacionais são lidas via JDBC com PySpark e salvas como Delta Lake no schema `bronze`. O modo é **full overwrite** — cada execução substitui a tabela inteira. Aplicamos **filtro temporal** no SQL Server para tabelas de eventos (pedidos, pagamentos, movimentações) respeitando a data atual. Toda tabela recebe metadados de linhagem (`_ingested_at`, `_source_path`).

2. **API PTAX → Bronze:** Cotações diárias de USD e EUR são buscadas via API HTTP do Banco Central. O modo é **incremental** com merge/upsert — apenas dias novos são inseridos. Suporta modo `full` para reprocessamento histórico.

**Etapa 2 — Validação**

O script `validate_extraction.py` verifica se todas as 25 tabelas Bronze (24 ERP + exchange_rates) foram carregadas com sucesso e possuem registros. Se alguma falhar, o pipeline é interrompido antes de prosseguir.

**Etapa 3 — Column Masking (Bronze)**

O script `apply_bronze_masks.py` aplica funções de máscara nas colunas sensíveis das tabelas Bronze (`customers`, `employees`, `suppliers`) via `ALTER TABLE SET MASK`.

**Etapa 4 — Transformação dbt**

Executa em sequência:

| Sub-etapa | Ação |
|-----------|------|
| `dbt deps` | Instala pacotes (dbt_utils) |
| `dbt run --select intermediate` | Materializa 24 tabelas no schema `silver` — limpeza, dedup, enriquecimento |
| `dbt test --select intermediate` | Executa testes de qualidade na camada Silver |
| `dbt run --select marts` | Materializa 12 modelos (6 dimensões + 6 fatos) no schema `gold` |
| `dbt test --select marts` | Executa testes de qualidade na camada Gold |
| `dbt run-operation apply_column_masks` | Aplica column masking nas tabelas Silver e Gold |

> **Nota:** O masking é executado como step explícito (`apply_masks`) após materialização e testes de todas as camadas, não via `on-run-end` no `dbt_project.yml`, para evitar falhas em execuções parciais.

### 5.2 Diagrama da arquitetura

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                          FONTES DE DADOS                                     │
├──────────────────────┬───────────────────────────────────────────────────────┤
│  ERP SQL Server      │              API PTAX (Banco Central)                │
│  24 tabelas          │              USD / EUR                               │
│  (clientes, produtos,│              Cotação de compra e venda               │
│   vendas, compras,   │                                                      │
│   estoque, etc.)     │                                                      │
└──────────┬───────────┴──────────────────────────┬────────────────────────────┘
           │                                      │
           ▼ JDBC (full)                          ▼ HTTP (incremental)
    ┌───────────────────────────────────────────────────────────┐
    │                BRONZE — Delta Lake                         │
    │          Catálogo: dev_lh_nautical / prod_lh_nautical      │
    │          Schema: bronze                                    │
    │                                                           │
    │   ┌──────────────┐  ┌──────────────┐  ┌────────────────┐ │
    │   │ customers     │  │ orders       │  │ exchange_rates │ │
    │   │ products      │  │ order_items  │  │                │ │
    │   │ suppliers     │  │ payments     │  │ USD, EUR       │ │
    │   │ ... (24)      │  │ stock_mov..  │  │                │ │
    │   └──────────────┘  └──────────────┘  └────────────────┘ │
    │                                                           │
    │   Metadados: _ingested_at, _source_path em todas as       │
    │   tabelas para rastreabilidade                            │
    └───────────────────────┬───────────────────────────────────┘
                            │
                            ▼ Validação (checagem de existência e contagem)
                            ▼ Column Masking (Bronze)
                            │
                    ┌───────┴───────────────────────────────────┐
                    │              dbt TRANSFORM                 │
                    │                                           │
                    │  ┌─────────────────────────────────────┐   │
                    │  │  STAGING (ephemeral — CTE)          │   │
                    │  │  Renomeação de colunas e tipagem    │   │
                    │  └──────────────┬──────────────────────┘   │
                    │                 │                          │
                    │  ┌──────────────┴──────────────────────┐   │
│  │  INTERMEDIATE (Silver — table)       │   │
│  │  Schema: silver                     │   │
│  │  24 tabelas                          │   │
                    │  │  Deduplicação, limpeza, correção,   │   │
                    │  │  enriquecimento, validação           │   │
                    │  │  Ex: int_customers, int_orders,     │   │
                    │  │  int_stock_movements                │   │
                    │  └──────────────┬──────────────────────┘   │
                    │                 │                          │
                    │  ┌──────────────┴──────────────────────┐   │
                    │  │  MARTS (Gold — table)                │   │
                    │  │  Schema: gold                       │   │
                    │  │  6 dimensões + 6 fatos              │   │
                    │  │  Star Schema                         │   │
                    │  │                                     │   │
                    │  │  Dimensões:      Fatos:             │   │
                    │  │  dim_date        fact_order_items   │   │
                    │  │  dim_customers   fact_payments      │   │
                    │  │  dim_employees   fact_purchase_     │   │
                    │  │  dim_locations     order_items      │   │
                    │  │  dim_products    fact_goods_receipt │   │
                    │  │  dim_suppliers     _items           │   │
                    │  │                   fact_stock_       │   │
                    │  │                     movements       │   │
                    │  │                   fact_return_items │   │
                    │  └─────────────────────────────────────┘   │
                    │                                           │
                    │  Ao final: apply_column_masks() em        │
                    │  Silver e Gold                            │
                    └───────────────────────────────────────────┘
                                        │
                                        ▼
               ┌─────────────────────────────────────────────┐
               │              CONSUMO (BI)                   │
               │                                             │
               │  fatos + dimensões no schema gold           │
               │  prontos para:                              │
               │  • Dashboards (Metabase / Power BI / Looker)│
               │  • Análises ad-hoc                          │
               │  • Relatórios financeiros                   │
               │  • Monitoramento de estoque                 │
               │  • Análise de devoluções e churn            │
               └─────────────────────────────────────────────┘
```

## 6. Stack tecnológica

| Categoria | Tecnologia |
|-----------|-----------|
| **Plataforma de Dados** | Databricks + Unity Catalog + Delta Lake |
| **Processamento** | PySpark (Spark Connect) 4.1 |
| **Transformação** | dbt-core 1.11 + dbt-databricks 1.12 |
| **Infraestrutura como Código** | Databricks Asset Bundles (DAB) |
| **Orquestração** | Databricks Jobs (multitask) |
| **CI/CD** | Bitbucket Pipelines |
| **Ingestão SQL Server** | JDBC + PySpark |
| **Ingestão API BCB** | requests + pandas |
| **Retry** | tenacity |
| **Qualidade** | pytest + dbt test (genérico + singular, 245+ testes) |
| **Linter SQL** | sqlfluff + sqlfluff-templater-dbt (convenção leading comma) |
| **Segurança** | Column Masking (Unity Catalog) |
| **Versionamento** | Git + Bitbucket |
| **Notificações** | Slack + E-mail |

## 7. Estrutura do repositório

```
lh_nautical/
├── databricks.yml                         # Config principal do DAB
├── dbt_project.yml                        # Config dbt (models, schemas)
├── profiles.yml                           # Conexão dbt → Databricks
├── bitbucket-pipelines.yml                # Pipeline CI/CD
├── requirements.txt                       # Dependências Python
├── resources/
│   ├── extract/
│   │   ├── extract_lh_nautical.yml        # Job: SQL Server → Bronze
│   │   ├── extract_exchange_rates.yml     # Job: API BCB → Bronze
│   │   └── generate_dab_lh_nautical.py    # Gerador automático do YAML
│   ├── transform/
│   │   └── dbt_transform.yml             # Job: transformação dbt
│   ├── orchestrator/
│   │   └── orchestrator_transform.yml    # Job: orquestrador principal (23:00 BRT)
│   └── security/
│       └── apply_bronze_masks.py          # Script para aplicar masks na Bronze
├── src/
│   ├── ingestion/
│   │   ├── config.py                      # Constantes (tabelas, JDBC URL)
│   │   ├── utils.py                       # Funções compartilhadas (Spark, Delta)
│   │   ├── extract_lh_nautical.py         # Extração SQL Server
│   │   ├── extract_exchange_rates.py      # Extração API BCB
│   │   └── validate_extraction.py         # Validador pós-extração
│   ├── dbt/
│   │   ├── models/
│   │   │   ├── staging/ (24 modelos)      # Cópia organizada dos dados brutos
│   │   │   ├── intermediate/ (24 modelos) # Limpeza e validação
│   │   │   └── marts/ (12 modelos)        # Modelo dimensional (Gold)
│   │   ├── macros/                        # Funções reutilizáveis
│   │   ├── tests/ (245+ testes)           # Testes de qualidade
│   │   └── run_dbt_step.py                # Wrapper para execução dbt
│   └── analytics_ai/                      # Previsão de demanda (ML) e RAG documental (Gen AI)
├── docs/                                  # Documentação completa
└── tests/                                 # Testes Python
```

## 8. Agendamento dos jobs

| Job | Horário (BRT) | Frequência |
|-----|--------------|------------|
| `orchestrator_transform` (pipeline completo) | 23:00 | Diário |
| `extract_lh_nautical` (24 tabelas ERP) | 00:00 e 18:00 | 2x ao dia |
| `extract_exchange_rates` (USD/EUR) | 18:00 | 1x ao dia |
| `dbt_transform` | Disparado pelo orchestrator | Sob demanda |

## 9. Equipe e contato

| Papel | Responsabilidade |
|-------|-----------------|
| **Tech Lead** | Gustavo Dias — arquitetura, revisão técnica, escalation |
| **Time de Dados (Athena / Indicium)** | Desenvolvimento, manutenção e evolução do pipeline |
| **Cliente** | LH Nautical |

**Canais de notificação:**

- Falhas em jobs: Slack `#lh-team-athena` + e-mail do tech lead
- Commits e PRs: Slack `#lh-team-athena`
- Deploy em produção: automático via Bitbucket Pipelines (push na `main`)

---

> **Status atual:** Pipeline implementado e em operação. A previsão de demanda por produto × loja já foi construída e avaliada em desenvolvimento (regressão linear, GLM e XGBoost contra uma régua simples; ver `docs/previsao_demanda_produto_loja.md`). Próximos passos incluem dashboards de BI, a decisão do modelo de previsão em produção, modelo de churn e assistentes inteligentes com Gen AI.
