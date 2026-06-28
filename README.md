# lh_nautical

Projeto de dados **LH Nautical** — pipeline completo para ingestão, transformação, visualização, machine learning e IA generativa no ecossistema Databricks, seguindo a **Arquitetura Medallion** (Bronze → Silver → Gold).

> **Fase atual:** Ingestão de dados do SQL Server (ERP) para a camada **Bronze**.
> **Próximas fases:** Transformações (dbt), dashboards, modelos ML e Gen AI.

---

## Navegação

- [1. Git — clonar o repositório](#1-git--clonar-o-repositório)
- [2. Databricks CLI — instalação e configuração](#2-databricks-cli--instalação-e-configuração)
- [3. Databricks Asset Bundle (DAB) — deploy](#3-databricks-asset-bundle-dab--deploy)
- [4. Conexão com o SQL Server](#4-conexão-com-o-sql-server)
- [5. Ambiente local (opcional — testes)](#5-ambiente-local-opcional--testes)
- [6. Estrutura do projeto](#6-estrutura-do-projeto)
- [7. Boas práticas](#7-boas-práticas)
- [Roadmap do projeto](#roadmap-do-projeto)
- [Documentação](#documentação)
- [Referências](#referências)

---

## Pré-requisitos

| Ferramenta                                                                   | Versão mín. | Finalidade                        |
| ---------------------------------------------------------------------------- | ----------- | --------------------------------- |
| [Python](https://www.python.org/downloads/)                                  | 3.10+       | Execução local / scripts auxiliares |
| [Git](https://git-scm.com/downloads)                                         | —           | Controle de versão                |
| [Databricks CLI](https://docs.databricks.com/en/dev-tools/cli/tutorial.html) | v1.x        | Deploy de bundles, execução de jobs |
| [Databricks workspace](https://docs.databricks.com/)                         | —           | Ambiente onde os jobs rodam       |

---

## 1. Git — clonar o repositório

```bash
# Clonar o projeto
git clone <url-do-repositorio>
cd lh_nautical

# Verificar o remote
git remote -v

# Criar uma branch para trabalhar (nunca trabalhe na main)
git checkout -b feat/minha-feature

# Verificar status dos arquivos
git status
```

### Boas práticas de commit

```bash
# Adicionar arquivos específicos (evite git add .)
git add src/ingestion/extract_lh_nautical.py
git add databricks.yml

# Commit com mensagem descritiva
git commit -m "feat: adiciona parametrização no script de extração"

# Convenção de mensagens:
#   feat:      nova funcionalidade
#   fix:       correção de bug
#   chore:     tarefa de manutenção
#   docs:      documentação
#   refactor:  mudança interna sem alterar comportamento

# Push para o remote
git push origin feat/minha-feature
```

> ⚠️ O diretório `.databricks/` está no `.gitignore` — é gerado localmente pela CLI e **nunca** deve ser versionado.

---

## 2. Databricks CLI — instalação e configuração

### Instalar

```bash
# Windows (PowerShell)
winget install Databricks.DatabricksCLI

# macOS (Homebrew)
brew install databricks/tap/databricks

# Linux (curl)
curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh | sh

# Verificar instalação
databricks --version
```

### Autenticação

Você precisa autenticar a CLI no seu workspace Databricks.

```bash
# Login interativo (abre o navegador)
databricks auth login --host https://<url-do-workspace>

# Verificar autenticação
databricks auth token --host https://<url-do-workspace>
```

> 💡 A URL do workspace tem o formato `https://dbc-xxxxx-xxxx.cloud.databricks.com`.

### Configurar um profile (opcional, mas recomendado)

```bash
# Listar profiles existentes
databricks auth profiles

# Criar um profile específico para o projeto
databricks auth login --host https://<url-do-workspace> --profile lh_nautical_dev
```

---

## 3. Databricks Asset Bundle (DAB) — deploy

Este projeto utiliza **Databricks Asset Bundles** para declarar jobs, permissões e recursos como código (YAML + Terraform).

### Estrutura do bundle

```
lh_nautical/
├── databricks.yml                     ← Config principal do bundle
├── .gitignore                         ← Arquivos ignorados pelo Git
├── README.md                          ← Esta documentação
├── bitbucket-pipelines.yml            ← Pipeline CI/CD (Bitbucket)
│
├── resources/
│   └── extract/
│       ├── extract_lh_nautical.yml    ← Job: SQL Server → Bronze (gerado)
│       ├── extract_exchange_rates.yml ← Job: API BCB → Bronze
│       └── generate_dab_lh_nautical.py ← Script gerador do YAML
│
├── src/
│   ├── ingestion/
│   │   ├── config.py                  ← Constantes (JDBC URL, tabelas, schemas)
│   │   ├── utils.py                   ← Funções compartilhadas (Spark, Delta)
│   │   ├── extract_lh_nautical.py     ← Extração: SQL Server → Bronze
│   │   └── extract_exchange_rates.py  ← Extração: API BCB → Bronze
│   ├── dbt/                           ← Ecossistema dbt
│   └── analytics_ai/                  ← ML e IA Generativa
│
├── docs/
│   ├── dab_configuration.md           ← Config do DAB e governança
│   ├── dictionary.md                  ← Dicionário de dados
│   ├── extract_lh_nautical.md         ← Docs: extração SQL Server
│   ├── extract_exchange_rates.md      ← Docs: extração API BCB
│   └── sp_prod_deploy.md              ← Docs: CI/CD e Service Principal
│
└── tests/                             ← Scripts de teste
```

### Comandos essenciais

```bash
# Validar a config do bundle (sem deploy)
databricks bundle validate

# Gerar o plano de deploy (mostra o que será criado/alterado)
databricks bundle plan --target dev

# Deploy no ambiente de dev
databricks bundle deploy --target dev

# Rodar o job imediatamente (após deploy)
databricks bundle run extract_lh_nautical --target dev

# Verificar status do job no terminal
databricks bundle run extract_lh_nautical --target dev --refresh-all

# Destruir recursos criados (cuidado!)
databricks bundle destroy --target dev
```

### Targets disponíveis

| Target | Unity Catalog      | Modo        | Uso                  |
| ------ | ------------------ | ----------- | -------------------- |
| `dev`  | `dev_lh_nautical`  | Development | Testes, iterações    |
| `prod` | `prod_lh_nautical` | Production  | Dados oficiais       |

```bash
# Deploy em produção (após testar no dev)
databricks bundle deploy --target prod

# Rodar o job em produção
databricks bundle run extract_lh_nautical --target prod
```

> ⚠️ Para deploy em produção, é recomendável usar uma **Service Principal** em vez de um usuário pessoal. Veja a seção de boas práticas.

---

## 4. Conexão com o SQL Server

O script de extração conecta ao SQL Server via JDBC. As credenciais são gerenciadas pelo **Databricks Secrets**, não por arquivos locais.

```bash
# Criar/atualizar um scope de segredos no Databricks (feito uma vez)
databricks secrets create-scope --scope lh_nautical

# Adicionar a senha do banco como segredo
databricks secrets put --scope lh_nautical --key secret_lh_nautical_bd
# (a CLI vai pedir o valor — digite a senha)

# Listar segredos existentes
databricks secrets list --scope lh_nautical
```

No código (`src/ingestion/extract_lh_nautical.py`), a senha é lida assim:

```python
password = dbutils.secrets.get("lh_nautical", "secret_lh_nautical_bd")
```

> 🔒 **Nunca** coloque senhas, tokens ou URLs completas em código versionado. **Sempre** use Databricks Secrets ou variáveis de ambiente.

---

## 5. Ambiente local (opcional — testes)

Se quiser testar scripts localmente com **Databricks Connect**:

```bash
# Criar ambiente virtual
python -m venv .venv

# Ativar
# Windows:
.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

# Instalar dependências
pip install -r requirements.txt

# Configurar variáveis de ambiente para o Databricks Connect
export DATABRICKS_HOST=https://<url-do-workspace>
export DATABRICKS_TOKEN=<seu-token>
```

Para rodar testes com pytest conectado ao Databricks:

```bash
pytest tests/ -v
```

> 💡 O arquivo `tests/conftest.py` já configura a sessão Spark via `DatabricksSession` para testes.

---

## 6. Estrutura do projeto

### Visão geral da arquitetura

```
      SQL Server (ERP)              API PTAX (BCB)
            │                              │
            ▼ ─── JDBC (full)              ▼ ─── HTTP (incremental)
┌─────────────────────────┐    ┌─────────────────────────┐
│    Bronze (ingestão)    │    │    Bronze (ingestão)    │
│  extract_lh_nautical.py │    │ extract_exchange_rates.py│
└───────────┬─────────────┘    └───────────┬─────────────┘
            │                              │
            └──────────────┬───────────────┘
                           │
                           ▼ ─── dbt
                  ┌─────────────────┐
                  │     Silver      │ ← Limpeza e padronização
                  └────────┬────────┘
                           │
                           ▼ ─── dbt
                  ┌─────────────────┐
                  │      Gold       │ ← Modelos analíticos de negócio
                  └────────┬────────┘
                           │
                           ├── → Dashboards (visualizações)
                           ├── → Machine Learning (modelos preditivos)
                           └── → Gen AI (assistentes inteligentes)
```

---

## 7. Boas práticas

### Git

- **Nunca** faça commit na branch `main` — sempre crie branches de funcionalidade.
- Use `.gitignore` para evitar versionar arquivos gerados, segredos, `.env`, `.databricks/`.
- Mantenha commits pequenos e descritivos.
- Sempre rode `git pull` antes de começar a trabalhar para evitar conflitos.

### Segurança

- **Nunca** versione senhas, tokens ou URLs internas.
- Use **Databricks Secrets** para credenciais de banco de dados.
- No target `prod`, configure uma **Service Principal** em vez de usar seu usuário pessoal.

```yaml
# databricks.yml (target prod)
run_as:
  service_principal_name: <id-da-service-principal>
```

### Deploy

- Sempre faça deploy e teste no `dev` antes de ir para o `prod`.
- Use `databricks bundle validate` para verificar erros de sintaxe.
- Revise o plano com `databricks bundle plan` antes de aplicar.

### Retry automático

Os scripts de extração possuem retry automático via biblioteca `tenacity`:

| Componente | Tentativas | Espera | Exceções |
|------------|------------|--------|----------|
| SQL Server | 3 | Exponencial (2s, 4s, 8s) | Qualquer Exception |
| API PTAX | 3 | Exponencial (2s, 4s, 8s) | RequestException, Timeout |

### Agendamento

Os jobs rodam automaticamente às **00:00** e **18:00** (horário de Brasília):

| Job | Horários |
|-----|----------|
| extract_lh_nautical | 00:00 e 18:00 |
| extract_exchange_rates | 00:00 e 18:00 |

### CI/CD (Bitbucket)

O pipeline `bitbucket-pipelines.yml` executa automaticamente ao fazer push na branch `main`:

1. Valida o bundle
2. Faz deploy em produção
3. Roda os jobs de extração

---

## Roadmap do projeto

| Fase                    | Entregável                                                               | Status     |
| ----------------------- | ------------------------------------------------------------------------ | ---------- |
| **Bronze** (ingestão)   | Extrair 24 tabelas do SQL Server para Unity Catalog                      | ⏳ Atual   |
| **Silver** (dbt)        | Limpeza, padronização, desduplicação e tipagem correta dos dados         | ⏳ Próximo |
| **Gold** (dbt)          | Modelos analíticos prontos para consumo (métricas de negócio, agregações)| ⏳ Futuro  |
| **Dashboards**          | Visualizações e dashboards (Databricks SQL ou ferramenta de BI)          | ⏳ Futuro  |
| **Machine Learning**    | Modelos preditivos (ex: previsão de demanda, churn, etc.)                | ⏳ Futuro  |
| **Gen AI**              | Assistentes inteligentes, análise em linguagem natural, recomendações    | ⏳ Futuro  |

---

## Documentação

| Documento | Descrição |
| --------- | --------- |
| `docs/dab_configuration.md` | Config do DAB, estrutura YAML, governança e permissões |
| `docs/dictionary.md` | Dicionário de dados (tabelas, colunas, relacionamentos) |
| `docs/extract_lh_nautical.md` | Docs: extração SQL Server → Bronze |
| `docs/extract_exchange_rates.md` | Docs: extração API BCB → Bronze |
| `docs/sp_prod_deploy.md` | Docs: CI/CD, Service Principal e deploy em produção |

---

## Referências

- [Databricks Asset Bundles — Documentação](https://docs.databricks.com/en/dev-tools/bundles/index.html)
- [Databricks CLI — Instalação](https://docs.databricks.com/en/dev-tools/cli/tutorial.html)
- [Databricks Secrets](https://docs.databricks.com/en/security/secrets/index.html)
- [Databricks Connect](https://docs.databricks.com/en/dev-tools/databricks-connect/index.html)
- [Conventional Commits](https://www.conventionalcommits.org/)
