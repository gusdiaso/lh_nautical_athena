# Orquestração da Transformação — lh_nautical

## Visão Geral

```
┌─────────────────────────────────────────────────────────────────────────┐
│                 orchestrator_transform (job)                             │
│                                                                         │
│  ┌─────────────────────┐    ┌───────────────────────────────┐           │
│  │ extract_lh_nautical │    │ extract_exchange_rates        │           │
│  │ (job - 24 tasks)    │    │ (job - 1 task)                │           │
│  └──────────┬──────────┘    └──────────┬────────────────────┘           │
│             │                          │                                │
│             └──────────┬───────────────┘                                │
│                        ▼                                                │
│             ┌──────────────────────┐                                    │
│             │  validate_extraction │  (verifica tabelas Bronze)         │
│             └──────────┬───────────┘                                    │
│                        ▼                                                │
│             ┌──────────────────────┐                                    │
│             │  apply_bronze_masks  │  (column masking na Bronze)        │
│             └──────────┬───────────┘                                    │
│                        ▼                                                │
│             ┌──────────────────┐                                        │
│             │  dbt_transform   │                                        │
│             │  (job - 5 tasks) │                                        │
│             └──────────────────┘                                        │
└─────────────────────────────────────────────────────────────────────────┘
```

O pipeline de dados é composto por **4 jobs do Databricks** que se coordenam:

| Job | Responsabilidade | Acionamento |
|-----|-----------------|-------------|
| `extract_lh_nautical` | Extrai 24 tabelas do SQL Server → Bronze | Pelo orchestrator ou schedule próprio |
| `extract_exchange_rates` | Extrai cotações PTAX (USD/EUR) → Bronze | Pelo orchestrator ou schedule próprio |
| `dbt_transform` | Transforma Bronze → Gold via dbt (staging é ephemeral) | Pelo orchestrator |
| `orchestrator_transform` | Coordena extração → validação → column masking → transformação dbt | Schedule único (23:00 BRT) |

---

## Jobs e Tasks

### 1. orchestrator_transform

Job principal que orquestra todo o pipeline.

**Schedule:** `0 0 23 * * ?` (23:00, horário de Brasília) — **ATIVO**.

**Tasks:**

| Task | Descrição | Depende de |
|------|-----------|------------|
| `extract_lh_nautical` | Executa o job de extração da LH Nautical | — |
| `extract_exchange_rates` | Executa o job de extração do Exchange Rates | — |
| `validate_extraction` | Verifica se todas as tabelas Bronze foram carregadas | `extract_lh_nautical` + `extract_exchange_rates` |
| `apply_bronze_masks` | Aplica column masking nas tabelas Bronze | `validate_extraction` |
| `dbt_transform` | Executa o job de transformação dbt | `apply_bronze_masks` |

As tasks de extração rodam **em paralelo**. A transformação só inicia após **ambas** finalizarem com sucesso e a validação + masking serem aplicadas.

### 2. extract_lh_nautical

Extrai todas as 24 tabelas do SQL Server (`lh_nautical.dbo`) para a camada Bronze no Databricks.

**Schedule:** `0 0 0,18 * * ?` (00:00 e 18:00 BRT) — **ATIVO**.

**Tasks:** 24 tasks paralelas (uma por tabela), cada uma executando `extract_lh_nautical.py --table <nome>`.

### 3. extract_exchange_rates

Extrai cotações diárias USD e EUR da API PTAX do Banco Central para a camada Bronze.

**Schedule:** `0 0 18 * * ?` (18:00 BRT) — **ATIVO**.

**Tasks:** 1 task executando `extract_exchange_rates.py` em modo incremental.

### 4. dbt_transform

Pipeline de transformação dbt completa. Executado pelo orchestrator ou manualmente (útil para reprocessamento).

**Schedule:** Acionado pelo orchestrator. Sem schedule próprio (dormant).

> **Sobre a sobreposição de schedules:** Os jobs `extract_lh_nautical` e `extract_exchange_rates` possuem schedules individuais (00:00/18:00 e 18:00 respectivamente) para permitir execuções avulsas fora da janela do orchestrator. Quando o `orchestrator_transform` dispara às 23:00, ele também executa esses mesmos jobs. Essa sobreposição é intencional — o schedule individual garante atualizações ao longo do dia, enquanto o orchestrator coordena o pipeline completo (extração → validação → masking → dbt) em uma única execução noturna.

**Tasks:**

| Task | Comando dbt | Depende de | Descrição |
|------|------------|------------|-----------|
| `deps` | `dbt deps` | — | Instala dependências (dbt_utils) |
| `intermediate_run` | `dbt run --select intermediate` | `deps` | Compila staging (ephemeral) + cria 24 tabelas no schema `silver` |
| `intermediate_test` | `dbt test --select intermediate` | `intermediate_run` | Testa dados da intermediate (inclui testes dos modelos staging) |
| `marts_run` | `dbt run --select marts` | `intermediate_test` | Cria 12 modelos (6 dimensões + 6 fatos) no schema `gold` |
| `marts_test` | `dbt test --select marts` | `marts_run` | Testa dados da camada marts |
| `apply_masks` | `dbt run-operation apply_column_masks` | `marts_test` | Aplica column masking nas tabelas Silver e Gold |

> **Nota:** O `on-run-end` foi removido do `dbt_project.yml` — o masking é executado como step explícito após todas as camadas estarem materializadas.

> **Por que essa ordem?** O dbt gerencia as dependências entre modelos automaticamente via `ref()`.
> A ordem sequencial por camada (staging → intermediate → marts) garante que cada camada
> seja **testada antes** de servir de insumo para a próxima, seguindo o mapeamento do
> [`mapeamento_dependencias.md`](mapeamento_dependencias.md).

---

## Dependências entre Modelos

O fluxo respeita a árvore de dependências documentada em [`mapeamento_dependencias.md`](mapeamento_dependencias.md):

### Staging (24 views)
Cada `stg_*` lê diretamente de uma tabela `bronze.*` — **sem dependências entre modelos staging**.

### Intermediate (24 tabelas)
Cada `int_*` depende do `stg_*` correspondente, com exceções:
- `int_purchase_orders` depende de `stg_purchase_orders` **e** `int_exchange_rates`
- `int_variant_attribute_values` depende de `stg_attributes` + `stg_variant_attribute_values`

O dbt resolve essas dependências automaticamente graças ao `{{ ref('int_exchange_rates') }}`.

### Marts (12 tabelas)
- **Dimensões** (6): dependem de modelos intermediate
- **Fatos** (6): dependem de intermediate + dimensões

Exemplo: `fact_order_items` depende de `dim_products`, `dim_customers`, `dim_locations`, `dim_employees`, `dim_date`, `int_order_items` e `int_orders`.

---

## Fluxo de Execução Detalhado

```
23:00 ─ orchestrator_transform inicia
        │
        ├── extract_lh_nautical (24 tasks paralelas ─ bronze)
        │
        └── extract_exchange_rates (1 task ─ bronze)
                │
                ▼ (ambos concluídos)
        ┌─────────────────────────────────────┐
        │  validate_extraction                │
        │  (checa todas as 25 tabelas Bronze) │
        └──────────────┬──────────────────────┘
                       ▼
        ┌─────────────────────────────────────┐
        │  apply_bronze_masks                 │
        │  (column masking em Bronze)         │
        └──────────────┬──────────────────────┘
                       ▼
        ┌──────────────────────────────────┐
        │        dbt_transform             │
        │                                  │
        │  deps                            │
        │    │                             │
        │    ▼                             │
        │  intermediate_run (24 tabelas)   │
        │    │                             │
        │    ▼                             │
        │  intermediate_test (testes int)  │
        │    │                             │
        │    ▼                             │
        │  marts_run (12 tabelas ─ gold)   │
        │    │                             │
        │    ▼                             │
        │  marts_test (testes marts)       │
        └──────────────────────────────────┘
                │
                ▼
        Pipeline concluído
```

---

## Como Executar

### Via Databricks CLI (DAB)

```bash
# Deploy dos recursos (jobs)
databricks bundle deploy -t dev

# Executar o orquestrador
databricks bundle run orchestrator_transform --target dev

# Executar apenas a transformação (útil para reprocessamento)
databricks bundle run dbt_transform --target dev

# Executar extrações individuais
databricks bundle run extract_lh_nautical --target dev
databricks bundle run extract_exchange_rates --target dev
```

### Via dbt (desenvolvimento local)

```bash
# Intermediate (staging é ephemeral — compilado como CTE junto)
dbt run --select intermediate --target dev
dbt test --select intermediate --target dev

# Marts
dbt run --select marts --target dev
dbt test --select marts --target dev
```

---

## Notificações

Os jobs enviam notificações por e-mail para `gustavou.dias@gmail.com`:

| Evento | Job | Notificação |
|--------|-----|-------------|
| Início | `orchestrator_transform` | `on_start` |
| Falha | Qualquer task | `on_failure` |
| Sucesso | *(sem notificação)* | — |

Para configurar outros destinatários, edite a propriedade `email_notifications` nos arquivos YAML dos jobs.

---

## Considerações sobre a Free Edition

O Databricks Free Edition (Community Edition) possui algumas limitações:

| Funcionalidade | Suportado | Observação |
|---------------|-----------|------------|
| Jobs (tarefas agendadas) | ✅ | Disponível |
| `run_job_task` | ✅ | Necessário para orquestração entre jobs |
| Job clusters | ✅ | Usado no `dbt_transform` |
| Repos / sync | ✅ | Via DAB |
| Unity Catalog | ⚠️ | Pode não estar disponível — usar schema `silver`/`gold` diretamente |

Se o Unity Catalog não estiver disponível, ajuste o `catalog` nos arquivos de configuração
ou use o schema padrão do metastore.

---

## Resolução de Problemas

### 1. Job de transformação falhou nos testes

Os testes da staging ou intermediate podem falhar se os dados da bronze estiverem inconsistentes.
Verifique:
```bash
# Rodar apenas os testes para diagnóstico
dbt test --select staging --target dev
```

### 2. Orquestrador não disparou a transformação

Verifique se ambos os jobs de extração concluíram com sucesso.
O `dbt_transform` só é acionado se `extract_lh_nautical` **e** `extract_exchange_rates` terminarem sem erro.

### 3. Reprocessar após correção

```bash
# Rodar apenas a transformação (sem extrair novamente)
databricks bundle run dbt_transform --target dev
```

### 4. Timeout em tasks grandes

Tasks como `marts_run` e `intermediate_run` têm timeout de 60 minutos.
Se exceder, aumente o `timeout_seconds` no YAML do job. Tasks comuns têm 30 minutos.
