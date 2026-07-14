# LH Nautical

## Descrição do Projeto

O **LH Nautical** é um pipeline de dados completo construído no ecossistema **Databricks**, seguindo a **Arquitetura Medallion** (Bronze → Silver → Gold). O projeto extrai dados de um ERP SQL Server (24 tabelas de domínio náutico/comercial) e cotações de moedas USD/EUR da API do Banco Central, salvando tudo como tabelas **Delta Lake** no Unity Catalog.

### Solução Atual (Bronze)

- **Ingestão SQL Server → Bronze**: Extração via JDBC de 24 tabelas (clientes, produtos, vendas, estoque, compras, etc.) com carga completa (full overwrite)
- **Ingestão API BCB → Bronze**: Extração incremental de cotações PTAX (USD/EUR) via HTTP com merge/upsert
- **Infraestrutura como Código**: Databricks Asset Bundles (DAB) para declarar jobs e permissões
- **CI/CD**: Pipeline automatizado via Bitbucket Pipelines (deploy em produção)
- **Retry Automático**: Tratamento de falhas de conexão com tenacity (3 tentativas, backoff exponencial)
- **Agendamento**: Jobs configurados para execução automática diária

### Próximas Fases

| Fase                 | Descrição                                                     | Status          |
| -------------------- | ------------------------------------------------------------- | --------------- |
| **Silver**           | Transformações com dbt: limpeza, padronização, desduplicação  | Em planejamento |
| **Gold**             | Modelos analíticos prontos para consumo (métricas de negócio) | Em planejamento |
| **Dashboards**       | Visualizações e relatórios                                    | Futuro          |
| **Machine Learning** | Modelos preditivos (previsão de demanda, churn)               | Futuro          |
| **Gen AI**           | Assistentes inteligentes e análise em linguagem natural       | Futuro          |

---

## Navegação

- [Descrição do Projeto](#descrição-do-projeto)
- [Passo a Passo: Executar o Pipeline](#passo-a-passo-executar-o-pipeline)
- [Comandos Úteis](#comandos-úteis)
- [Ambiente Local](#ambiente-local-opcional---testes)
- [Estrutura do Projeto](#estrutura-do-projeto)
- [Arquitetura](#arquitetura)
- [Documentação](#documentação)
- [Referências](#referências)
- [Boas Práticas e Dicas](#boas-práticas-e-dicas)

---

## Passo a Passo: Executar o Pipeline

### Pré-requisitos

| Ferramenta                                                                   | Versão mín. | Instalação                                |
| ---------------------------------------------------------------------------- | ----------- | ----------------------------------------- |
| [Python](https://www.python.org/downloads/)                                  | 3.10+       | `winget install Python.Python.3.12`       |
| [Git](https://git-scm.com/downloads)                                         | —           | `winget install Git.Git`                  |
| [Databricks CLI](https://docs.databricks.com/en/dev-tools/cli/tutorial.html) | v1.x        | `winget install Databricks.DatabricksCLI` |

### Passo 1: Clonar o repositório

```bash
git clone <url-do-repositorio>
cd lh_nautical
```

### Passo 2: Autenticar a CLI no Databricks

```bash
# Login interativo (abre o navegador)
databricks auth login --host https://<url-do-workspace>

# Verificar autenticação
databricks auth token --host https://<url-do-workspace>
```

> A URL do workspace tem o formato `https://dbc-xxxxx-xxxx.cloud.databricks.com`.

### Passo 3: Configurar segredos (uma única vez)

```bash
# Criar scope de segredos
databricks secrets create-scope --scope lh_nautical

# Adicionar senha do SQL Server
databricks secrets put --scope lh_nautical --key secret_lh_nautical_bd
# (digite a senha quando solicitado)
```

### Passo 4: Validar o bundle

```bash
databricks bundle validate
```

### Passo 5: Deploy e execução

```bash
# Deploy em desenvolvimento
databricks bundle deploy --target dev

# Rodar o job de extração SQL Server
databricks bundle run extract_lh_nautical --target dev

# Rodar o job de extração de cotações
databricks bundle run extract_exchange_rates --target dev
```

### Passo 6: Verificar resultados

- Acesse o Databricks Workspace → Catalog → `dev_lh_nautical` → `bronze`
- Verifique as 25 tabelas Delta Lake criadas (24 do SQL Server + 1 de exchange rates)

---

## Comandos Úteis

```bash
# Validar bundle (sem deploy)
databricks bundle validate

# Ver plano de deploy
databricks bundle plan --target dev

# Deploy em produção (após testar no dev)
databricks bundle deploy --target prod

# Rodar jobs em produção
databricks bundle run extract_lh_nautical --target prod
databricks bundle run extract_exchange_rates --target prod

# Destruir recursos criados (cuidado!)
databricks bundle destroy --target dev
```

---

## Ambiente Local (Opcional - Testes)

```bash
# Criar ambiente virtual
python -m venv .venv

# Ativar (Windows)
.venv\Scripts\Activate.ps1

# Instalar dependências
pip install -r requirements.txt

# Configurar variáveis de ambiente para Databricks Connect
set DATABRICKS_HOST=https://<url-do-workspace>
set DATABRICKS_TOKEN=<seu-token>

# Rodar testes unitários (sem conexão com Databricks)
pytest tests/ -v

# Rodar testes com conexão Databricks (requer compute ativo)
pytest tests/ -v --databricks
```

---

## Estrutura do Projeto

```
lh_nautical/
├── databricks.yml                         # Config principal do DAB
├── bitbucket-pipelines.yml                # Pipeline CI/CD
├── requirements.txt                       # Dependências Python
├── resources/
│   └── extract/
│       ├── extract_lh_nautical.yml        # Job: SQL Server → Bronze
│       ├── extract_exchange_rates.yml     # Job: API BCB → Bronze
│       └── generate_dab_lh_nautical.py    # Gerador automático do YAML
├── src/
│   ├── ingestion/
│   │   ├── config.py                      # Constantes (tabelas, JDBC URL)
│   │   ├── utils.py                       # Funções compartilhadas (Spark, Delta)
│   │   ├── extract_lh_nautical.py         # Extração SQL Server
│   │   └── extract_exchange_rates.py      # Extração API BCB
│   ├── dbt/                               # Transformações dbt (futuro)
│   └── analytics_ai/                      # ML e Gen AI (futuro)
├── docs/                                  # Documentação
│   ├── dictionary.md                      # Dicionário de dados
│   ├── extract_lh_nautical.md             # Docs extração SQL Server
│   ├── extract_exchange_rates.md          # Docs extração API BCB
│   ├── dab_configuration.md               # Configuração DAB
│   └── sp_prod_deploy.md                  # CI/CD e Service Principal
└── tests/
    ├── notebooks/                         # Notebooks de teste
    └── sql/                               # Scripts SQL de teste
```

---

## Arquitetura

```
SQL Server (ERP)                API PTAX (BCB)
       │                              │
       ▼ ─── JDBC (full)              ▼ ─── HTTP (incremental)
┌─────────────────────────┐    ┌─────────────────────────┐
│    BRONZE (ATUAL)       │    │    BRONZE (ATUAL)       │
│  24 tabelas Delta Lake  │    │  exchange_rates Delta   │
└───────────┬─────────────┘    └───────────┬─────────────┘
            │                              │
            └──────────────┬───────────────┘
                           │
                           ▼ ─── dbt (FUTURO)
                  ┌─────────────────┐
                  │     SILVER      │
                  └────────┬────────┘
                           │
                           ▼ ─── dbt (FUTURO)
                  ┌─────────────────┐
                  │      GOLD       │
                  └────────┬────────┘
                           │
                           ├── → Dashboards
                           ├── → Machine Learning
                           └── → Gen AI
```

---

## Documentação

| Documento                        | Descrição                                                  |
| -------------------------------- | ---------------------------------------------------------- |
| `docs/dictionary.md`             | Dicionário de dados (24 tabelas, colunas, relacionamentos) |
| `docs/marts.md`                  | Guia de leitura da camada marts e das decisões de modelagem |
| `docs/extract_lh_nautical.md`    | Detalhes da extração SQL Server → Bronze                   |
| `docs/extract_exchange_rates.md` | Detalhes da extração API BCB → Bronze                      |
| `docs/dab_configuration.md`      | Configuração do DAB e governança                           |
| `docs/sp_prod_deploy.md`         | CI/CD e Service Principal                                  |

---

## Referências

- [Databricks Asset Bundles](https://docs.databricks.com/en/dev-tools/bundles/index.html)
- [Databricks CLI](https://docs.databricks.com/en/dev-tools/cli/tutorial.html)
- [Databricks Secrets](https://docs.databricks.com/en/security/secrets/index.html)
- [API PTAX Banco Central](https://olinda.bcb.gov.br/olinda/servico/PTAX)

---

## Boas Práticas e Dicas

### Git

```bash
# Criar branch para trabalhar (nunca trabalhe na main)
git checkout -b feat/minha-feature

# Adicionar arquivos específicos (evite git add .)
git add src/ingestion/extract_lh_nautical.py

# Commit com mensagem descritiva
git commit -m "feat: adiciona parametrização no script de extração"
```

**Convenção de mensagens:**
| Prefixo | Uso |
|---------|-----|
| `feat` | Nova funcionalidade |
| `fix` | Correção de bug |
| `chore` | Tarefa de manutenção |
| `docs` | Documentação |
| `refactor` | Mudança sem alterar comportamento |

> O diretório `.databricks/` está no `.gitignore` — é gerado localmente pela CLI e **nunca** deve ser versionado.

### Segurança

- **Nunca** versione senhas, tokens ou URLs internas
- Use **Databricks Secrets** para credenciais de banco de dados
- No target `prod`, configure uma **Service Principal** em vez de usar seu usuário pessoal

### Deploy

- Sempre faça deploy e teste no `dev` antes de ir para o `prod`
- Use `databricks bundle validate` para verificar erros de sintaxe
- Revise o plano com `databricks bundle plan` antes de aplicar

### Retry automático

Os scripts de extração possuem retry automático via biblioteca `tenacity`:

| Componente | Tentativas | Espera                   | Exceções                  |
| ---------- | ---------- | ------------------------ | ------------------------- |
| SQL Server | 3          | Exponencial (2s, 4s, 8s) | Qualquer Exception        |
| API PTAX   | 3          | Exponencial (2s, 4s, 8s) | RequestException, Timeout |

### Agendamento dos Jobs

Os jobs rodam automaticamente conforme configuração nos YAMLs:

| Job                    | Horários      | Frequência |
| ---------------------- | ------------- | ---------- |
| extract_lh_nautical    | 00:00 e 18:00 | 2x ao dia  |
| extract_exchange_rates | 18:00         | 1x ao dia  |

### CI/CD (Bitbucket)

O pipeline `bitbucket-pipelines.yml` executa automaticamente ao fazer push na branch `main`:

1. Instala a CLI do Databricks
2. Faz deploy em produção (`databricks bundle deploy -t prod`)
3. Roda os jobs de extração (`databricks bundle run ...`)

**Autenticação:** Via variáveis de ambiente do Bitbucket (`DATABRICKS_HOST`, `DATABRICKS_CLIENT_ID`, `DATABRICKS_CLIENT_SECRET`) — nunca no código.
