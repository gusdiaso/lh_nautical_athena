# lh_nautical

**LH Nautical** data project — a complete pipeline for ingestion, transformation, visualization, machine learning, and generative AI on the Databricks ecosystem, following the **Medallion Architecture** (Bronze → Silver → Gold).

> **Current phase:** Ingesting data from SQL Server (ERP) into the **Bronze** layer.  
> **Next phases:** Transformations (dbt), dashboards, ML models, and Gen AI.

---

## Navigation

- [1. Git — clone the repository](#1-git--clone-the-repository)
- [2. Databricks CLI — installation & setup](#2-databricks-cli--installation--setup)
- [3. Databricks Asset Bundle (DAB) — deploy](#3-databricks-asset-bundle-dab--deploy)
- [4. SQL Server connection](#4-sql-server-connection)
- [5. Local environment (optional — testing)](#5-local-environment-optional--testing)
- [6. Project structure](#6-project-structure)
- [7. Best practices](#7-best-practices)
- [Project roadmap](#project-roadmap)
- [References](#references)

---

## Prerequisites

| Tool                                                                         | Min. version | Purpose                          |
| ---------------------------------------------------------------------------- | ------------ | -------------------------------- |
| [Python](https://www.python.org/downloads/)                                  | 3.10+        | Local execution / helper scripts |
| [Git](https://git-scm.com/downloads)                                         | —            | Version control                  |
| [Databricks CLI](https://docs.databricks.com/en/dev-tools/cli/tutorial.html) | v1.x         | Bundle deploy, job execution     |
| [Databricks workspace](https://docs.databricks.com/)                         | —            | Environment where jobs run       |

---

## 1. Git — clone the repository

```bash
# Clone the project
git clone <repository-url>
cd lh_nautical

# Check the remote
git remote -v

# Create a branch to work on (never work on main)
git checkout -b feat/my-feature

# Check file status
git status
```

### Commit best practices

```bash
# Add specific files (avoid git add .)
git add src/ingestion/extract_lh_nautical.py
git add databricks.yml

# Commit with a descriptive message
git commit -m "feat: add parameterization to extraction script"

# Message convention:
#   feat:      new feature
#   fix:       bug fix
#   chore:     maintenance task
#   docs:      documentation
#   refactor:  internal change without behavior change

# Push to remote
git push origin feat/my-feature
```

> ⚠️ The `.databricks/` directory is in `.gitignore` — it is generated locally by the CLI and should **never** be versioned.

---

## 2. Databricks CLI — installation & setup

### Install

```bash
# Windows (PowerShell)
winget install Databricks.DatabricksCLI

# macOS (Homebrew)
brew install databricks/tap/databricks

# Linux (curl)
curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh | sh

# Verify installation
databricks --version
```

### Authentication

You need to authenticate the CLI to your Databricks workspace.

```bash
# Interactive login (opens browser)
databricks auth login --host https://<workspace-url>

# Verify authentication
databricks auth token --host https://<workspace-url>
```

> 💡 The workspace URL looks like `https://dbc-xxxxx-xxxx.cloud.databricks.com`.

### Configure a profile (optional but recommended)

```bash
# List existing profiles
databricks auth profiles

# Create a project-specific profile
databricks auth login --host https://<workspace-url> --profile lh_nautical_dev
```

---

## 3. Databricks Asset Bundle (DAB) — deploy

This project uses **Databricks Asset Bundles** to declare jobs, permissions, and resources as code (YAML + Terraform).

### Bundle structure

```
lh_nautical/
├── databricks.yml                      ← Main bundle config
├── .gitignore                          ← Git-ignored files
├── README.en.md                        ← This documentation
│
├── resources/
│   └── extract/
│       └── extract_lh_nautical.yml     ← Extraction job definition
│
├── src/                                ← Source code (Python, notebooks, dbt)
│   ├── ingestion/                      ← Data extraction scripts
│   │   └── extract_lh_nautical.py
│   ├── dbt/                            ← dbt ecosystem
│   └── analytics_ai/                   ← ML and Generative AI
│
└── tests/                              → Test scripts

```

### Essential commands

```bash
# Validate the bundle config (without deploying)
databricks bundle validate

# Generate the deployment plan (shows what will be created/changed)
databricks bundle plan --target dev

# Deploy to dev environment
databricks bundle deploy --target dev

# Run the job immediately (after deploy)
databricks bundle run extract_lh_nautical --target dev

# Check job status in terminal
databricks bundle run extract_lh_nautical --target dev --refresh-all

# Destroy created resources (careful!)
databricks bundle destroy --target dev
```

### Available targets

| Target | Unity Catalog      | Mode        | Usage               |
| ------ | ------------------ | ----------- | ------------------- |
| `dev`  | `dev_lh_nautical`  | Development | Testing, iterations |
| `prod` | `prod_lh_nautical` | Production  | Official data       |

```bash
# Deploy to production (after testing in dev)
databricks bundle deploy --target prod

# Run the job in production
databricks bundle run extract_lh_nautical --target prod
```

> ⚠️ For production deploy, it is recommended to use a **Service Principal** instead of a personal user. See the best practices section.

---

## 4. SQL Server connection

The extraction script connects to SQL Server via JDBC. Credentials are managed by **Databricks Secrets**, not by local files.

```bash
# Create/update a secret scope in Databricks (done once)
databricks secrets create-scope --scope lh_nautical

# Add the database password as a secret
databricks secrets put --scope lh_nautical --key secret_lh_nautical_bd
# (the CLI will ask for the value — type the password)

# List existing secrets
databricks secrets list --scope lh_nautical
```

In the code (`src/ingestion/extract_lh_nautical.py`), the password is read like this:

```python
password = dbutils.secrets.get("lh_nautical", "secret_lh_nautical_bd")
```

> 🔒 **Never** put passwords, tokens, or full URLs in versioned code. **Always** use Databricks Secrets or environment variables.

---

## 5. Local environment (optional — testing)

If you want to test scripts locally with **Databricks Connect**:

```bash
# Create virtual environment
python -m venv .venv

# Activate
# Windows:
.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

# Install dependencies (if requirements.txt exists)
pip install -r requirements.txt

# Set environment variables for Databricks Connect
export DATABRICKS_HOST=https://<workspace-url>
export DATABRICKS_TOKEN=<your-token>
```

To run tests with pytest connected to Databricks:

```bash
pytest tests/ -v
```

> 💡 The `tests/conftest.py` file already sets up the Spark session via `DatabricksSession` for testing.

---

## 6. Project structure

### Architecture overview

```
      SQL Server (ERP)
            │
            ▼ ─── JDBC (full/incremental)
┌─────────────────────────┐
│    Bronze (ingestion)   │  ← Spark Python (src/ingestion/)
└───────────┬─────────────┘
            │
            ▼ ─── dbt
┌─────────────────────────┐
│         Silver          │  ← Cleaning & standardization
└───────────┬─────────────┘
            │
            ▼ ─── dbt
┌─────────────────────────┐
│          Gold           │  ← Business analytics models
└───────────┬─────────────┘
            │
            ├── → Dashboards (visualizations)
            ├── → Machine Learning (predictive models)
            └── → Gen AI (intelligent assistants)
```

---

## 7. Best practices

### Git

- **Never** commit to the `main` branch — always create feature branches.
- Use `.gitignore` to avoid versioning generated files, secrets, `.env`, `.databricks/`.
- Keep commits small and descriptive.
- Always run `git pull` before starting work to avoid conflicts.

### Security

- **Never** version passwords, tokens, or internal URLs.
- Use **Databricks Secrets** for database credentials.
- In the `prod` target, configure a **Service Principal** instead of using your personal user.

```yaml
# databricks.yml (prod target)
run_as:
  service_principal_name: <service-principal-id>
```

### Deploy

- Always deploy and test in `dev` before going to `prod`.
- Use `databricks bundle validate` to check for syntax errors.
- Review the plan with `databricks bundle plan` before applying.

---

## Project roadmap

| Phase                  | Deliverable                                                             | Status     |
| ---------------------- | ----------------------------------------------------------------------- | ---------- |
| **Bronze** (ingestion) | Extract all 24 tables from SQL Server to Unity Catalog                  | ⏳ Current |
| **Silver** (dbt)       | Data cleaning, standardization, deduplication, correct typing           | ⏳ Next    |
| **Gold** (dbt)         | Analytics models ready for consumption (business metrics, aggregations) | ⏳ Future  |
| **Dashboards**         | Visualizations and dashboards (Databricks SQL or BI tool)               | ⏳ Future  |
| **Machine Learning**   | Predictive models (e.g., demand forecasting, churn, etc.)               | ⏳ Future  |
| **Gen AI**             | Intelligent assistants, natural language analysis, recommendations      | ⏳ Future  |

---

## References

- [Databricks Asset Bundles — Documentation](https://docs.databricks.com/en/dev-tools/bundles/index.html)
- [Databricks CLI — Installation](https://docs.databricks.com/en/dev-tools/cli/tutorial.html)
- [Databricks Secrets](https://docs.databricks.com/en/security/secrets/index.html)
- [Databricks Connect](https://docs.databricks.com/en/dev-tools/databricks-connect/index.html)
- [Conventional Commits](https://www.conventionalcommits.org/)
