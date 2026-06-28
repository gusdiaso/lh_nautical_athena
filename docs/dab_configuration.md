# Configuracao do DAB (Databricks Asset Bundles)

## O que e um DAB?

**DAB** significa **Databricks Asset Bundle**. E uma forma de configurar jobs, permissoes e recursos do Databricks usando arquivos YAML (um tipo de arquivo de configuracao).

**Pense assim:** Em vez de criar jobs clicando na interface do Databricks, voce escreve um arquivo YAML e o Databricks cria tudo automaticamente.

---

## Por que usar DAB?

| Antes (interface) | Depois (DAB) |
|-------------------|--------------|
| Clicar para criar job | Escrever YAML |
| Configurar manualmente | Configuracao versionada no Git |
| Dificil de reproduzir | Mesma config em qualquer ambiente |
| Sem historico de mudancas | Git controla todas as alteracoes |

---

## Estrutura de Arquivos

```
lh_nautical/
├── databricks.yml                         # Configuracao principal do bundle
├── resources/
│   └── extract/
│       ├── extract_lh_nautical.yml        # Job: SQL Server → Bronze
│       ├── extract_exchange_rates.yml     # Job: API BCB → Bronze
│       └── generate_dab_lh_nautical.py    # Gerador automatico do YAML
└── src/
    └── ingestion/
        ├── config.py                      # Constantes
        ├── utils.py                       # Funcoes compartilhadas
        ├── extract_lh_nautical.py         # Codigo: SQL Server
        └── extract_exchange_rates.py      # Codigo: API BCB
```

---

## Arquivo Principal: databricks.yml

```yaml
# Nome e identificacao do bundle
bundle:
  name: lh_nautical
  uuid: 6cbf77ec-43aa-4f6b-8cde-df1732439764

# Quais arquivos YAML incluir
include:
  - resources/*.yml
  - resources/*/*.yml

# Quais arquivos Python sincronizar
sync:
  include:
    - src/*/*.py

# Quem pode acessar o bundle
permissions:
  - user_name: ${workspace.current_user.userName}
    level: CAN_MANAGE
  - group_name: lh_nautical_dev
    level: CAN_VIEW

# Workspace de destino
workspace:
  host: https://dbc-c4e046bc-37b5.cloud.databricks.com

# Ambientes (dev e prod)
targets:
  dev:
    default: true
    mode: development
    permissions:
      - group_name: lh_nautical_dev
        level: CAN_MANAGE

  prod:
    mode: production
    permissions:
      - group_name: lh_nautical_prod
        level: CAN_VIEW
    git:
      branch: main
    run_as:
      service_principal_name: '1d6b3e3c-c04d-41e0-9883-ae8d467adcaf'
```

---

## O que cada secao faz

### 1. bundle (identificacao)

```yaml
bundle:
  name: lh_nautical
  uuid: 6cbf77ec-43aa-4f6b-8cde-df1732439764
```

| Campo  | O que e                                         |
| ------ | ----------------------------------------------- |
| `name` | Nome do bundle ( aparece no Databricks)        |
| `uuid` | Identificador unico (gerado automaticamente)   |

### 2. include (arquivos YAML)

```yaml
include:
  - resources/*.yml
  - resources/*/*.yml
```

Diz ao Databricks **quais arquivos YAML** ele deve ler para criar os jobs.

- `resources/*.yml` = todos os YAMLs na pasta `resources/`
- `resources/*/*.yml` = todos os YAMLs em subpastas de `resources/`

### 3. sync (arquivos Python)

```yaml
sync:
  include:
    - src/*/*.py
```

Diz ao Databricks **quais arquivos Python** ele deve enviar para o workspace.

- `src/*/*.py` = todos os arquivos `.py` dentro de subpastas de `src/`

### 4. permissions (permissoes)

```yaml
permissions:
  - user_name: ${workspace.current_user.userName}
    level: CAN_MANAGE
  - group_name: lh_nautical_dev
    level: CAN_VIEW
  - group_name: lh_nautical_prod
    level: CAN_VIEW
```

Define **quem pode acessar** o bundle.

| Nivel        | O que permite                              |
| ------------ | ------------------------------------------ |
| `CAN_MANAGE` | Criar, editar, excluir e executar jobs     |
| `CAN_VIEW`   | Apenas visualizar e executar jobs          |

### 5. targets (ambientes)

```yaml
targets:
  dev:
    default: true
    mode: development
    permissions:
      - group_name: lh_nautical_dev
        level: CAN_MANAGE

  prod:
    mode: production
    permissions:
      - group_name: lh_nautical_prod
        level: CAN_VIEW
    git:
      branch: main
    run_as:
      service_principal_name: '1d6b3e3c-c04d-41e0-9883-ae8d467adcaf'
```

| Campo              | `dev`             | `prod`              |
| ------------------ | ----------------- | ------------------- |
| `mode`             | `development`     | `production`        |
| `default`          | `true`            | -                   |
| `branch`           | Qualquer          | `main`              |
| `permissao`        | `CAN_MANAGE`      | `CAN_VIEW`          |
| `run_as`           | -                 | Service Principal   |

---

## Job: extract_lh_nautical.yml

```yaml
# Variaveis reutilizaveis
variables:
  catalog:
    description: 'Catalogo no Unity Catalog'
  schema:
    description: 'Schema de destino no Unity Catalog'
    default: bronze

# Valores por ambiente
targets:
  dev:
    variables:
      catalog: dev_lh_nautical
      schema: bronze
  prod:
    variables:
      catalog: prod_lh_nautical
      schema: bronze

# Configuracao do job
resources:
  jobs:
    extract_lh_nautical:
      name: extract_lh_nautical
      description: 'Job que extrai tabelas do SQL Server para Bronze.'
      max_concurrent_runs: 1
      
      schedule:
        quartz_cron_expression: '0 0 18 * * ?'
        timezone_id: 'America/Sao_Paulo'
        pause_status: UNPAUSED
      
      environments:
        - environment_key: default
          spec:
            environment_version: '2'
            dependencies: []
      
      # Uma task por tabela (24 tabelas)
      tasks:
        - task_key: extract_order_items
          environment_key: default
          spark_python_task:
            python_file: ../../src/ingestion/extract_lh_nautical.py
            parameters:
              - --table
              - order_items
              - --catalog
              - ${var.catalog}
              - --schema
              - ${var.schema}
        # ... mais 23 tasks ...
```

### Explicacao simples

| Campo                | O que faz                                    |
| -------------------- | -------------------------------------------- |
| `variables`          | Cria variaveis que podem ser reutilizadas    |
| `targets`            | Define valores para cada ambiente            |
| `schedule`           | Executa o job automaticamente                |
| `max_concurrent_runs`| So roda 1 execucao por vez                   |
| `tasks`              | Lista de tarefas (1 por tabela)              |
| `python_file`        | Caminho do script Python                     |
| `parameters`         | Parametros passados para o script            |

### Schedule (Cron)

```yaml
schedule:
  quartz_cron_expression: '0 0 18 * * ?'
  timezone_id: 'America/Sao_Paulo'
  pause_status: UNPAUSED
```

| Parte     | Significado            |
| --------- | ---------------------- |
| `0`       | Segundo (0)            |
| `0`       | Minuto (0)             |
| `18`      | Hora (18h)             |
| `*`       | Qualquer dia           |
| `*`       | Qualquer mes           |
| `?`       | Qualquer dia da semana |

**Resultado:** Executa todo dia as 18:00 (horario de Brasilia)

---

## Job: extract_exchange_rates.yml

```yaml
# Variaveis reutilizaveis
variables:
  catalog:
    description: 'Catalogo no Unity Catalog'
  schema:
    description: 'Schema de destino no Unity Catalog'
    default: bronze

# Valores por ambiente
targets:
  dev:
    variables:
      catalog: dev_lh_nautical
      schema: bronze
  prod:
    variables:
      catalog: prod_lh_nautical
      schema: bronze

# Configuracao do job
resources:
  jobs:
    extract_exchange_rates:
      name: extract_exchange_rates
      description: 'Job diario que ingere cotacoes PTAX do Banco Central.'
      max_concurrent_runs: 1
      
      schedule:
        quartz_cron_expression: '0 0 18 * * ?'
        timezone_id: 'America/Sao_Paulo'
        pause_status: UNPAUSED
      
      environments:
        - environment_key: default
          spec:
            environment_version: '2'
            dependencies:
              - requests
              - pandas
              - tenacity
      
      # 1 unica task
      tasks:
        - task_key: extract_bcb_exchange_rates
          environment_key: default
          spark_python_task:
            python_file: ../../src/ingestion/extract_exchange_rates.py
            parameters:
              - --catalog
              - ${var.catalog}
              - --schema
              - ${var.schema}
              - --start-date
              - '2019-07-01'
              - --load-mode
              - incremental
```

### Diferenca para o outro job

| Campo           | `extract_lh_nautical` | `extract_exchange_rates` |
| --------------- | --------------------- | ------------------------ |
| Tasks           | 24 (1 por tabela)     | 1                        |
| Dependencies    | `['tenacity']`        | `['requests', 'pandas', 'tenacity']` |
| Parametros      | `--table`             | `--start-date`, `--load-mode` |

---

## Governanca e Permissoes

### Hierarquia de Permissoes

```
┌─────────────────────────────────────────────────────┐
│                    Databricks                       │
├─────────────────────────────────────────────────────┤
│  Bundle: lh_nautical                               │
│  │                                                 │
│  ├── Permissoes Gerais (databricks.yml)           │
│  │   ├── current_user: CAN_MANAGE                 │
│  │   ├── lh_nautical_dev: CAN_VIEW                │
│  │   └── lh_nautical_prod: CAN_VIEW               │
│  │                                                 │
│  ├── Ambiente dev                                  │
│  │   └── lh_nautical_dev: CAN_MANAGE              │
│  │                                                 │
│  └── Ambiente prod                                 │
│      ├── lh_nautical_prod: CAN_VIEW               │
│      └── Branch: main                              │
└─────────────────────────────────────────────────────┘
```

### Tabela de Permissoes

| Grupo               | dev         | prod        | O que pode fazer           |
| ------------------- | ----------- | ----------- | -------------------------- |
| `current_user`      | `CAN_MANAGE`| `CAN_MANAGE`| Tudo (admin)               |
| `lh_nautical_dev`   | `CAN_MANAGE`| `CAN_VIEW`  | Gerenciar dev, ver prod    |
| `lh_nautical_prod`  | `CAN_VIEW`  | `CAN_VIEW`  | Apenas visualizar          |

---

## Comandos Utis

```bash
# Validar se os YAMLs estao corretos
databricks bundle validate

# Ver o que vai ser criado/alterado
databricks bundle plan --target dev

# Enviar para o Databricks (dev)
databricks bundle deploy --target dev

# Enviar para o Databricks (prod)
databricks bundle deploy --target prod

# Executar um job
databricks bundle run extract_lh_nautical --target dev

# Executar um job (prod)
databricks bundle run extract_lh_nautical --target prod

# Apagar tudo (cuidado!)
databricks bundle destroy --target dev
```

---

## Fluxo de Trabalho

```
1. Escrever/editar YAMLs
         │
         ▼
2. Validar (bundle validate)
         │
         ▼
3. Deploy para dev (bundle deploy --target dev)
         │
         ▼
4. Testar (bundle run ...)
         │
         ▼
5. Deploy para prod (bundle deploy --target prod)
```
