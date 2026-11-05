🇧🇷 [Português](README.md) | 🇺🇸 English

# LH Nautical — Databricks Data Platform

End-to-end data platform built on **Databricks** for a simulated nautical retail chain (3 warehouses and 3 stores). Capstone project of the Indicium Lighthouse program, developed by a team of three. The company and its data are part of a simulated case.

> This page is an English overview. The full operational guide (commands, environment setup, security, documentation index) is in the [Portuguese README](README.md), and the detailed technical documents in `docs/` are also in Portuguese.

## What it covers

| Track | What it does | Where |
|-------|--------------|-------|
| **Ingestion** | Extracts 24 tables from a SQL Server ERP and daily USD/EUR rates from the Brazilian Central Bank (PTAX) API into **Delta Lake** tables (Bronze layer) | `src/ingestion/` |
| **Transformation** | dbt applies the **Medallion Architecture** (Bronze → Silver → Gold) and delivers a dimensional model with 6 dimensions and 6 facts, plus demand and feature tables for ML (`ml` schema) | `src/dbt/` |
| **Demand forecasting (ML)** | Forecasts the next 3 months of sales per product × store with a statistical baseline and three compared models (Linear Regression, Poisson/Tweedie GLM, XGBoost), and analyzes growth by distribution center and store | `src/analytics_ai/demand_*.py`, `notebooks/ml/` |
| **Document RAG (Gen AI)** | Answers natural-language questions about the project's technical documentation, with verifiable citations and no access to the data warehouse | `src/analytics_ai/rag_*.py`, `apps/rag_chat/` |

Everything runs on Unity Catalog (`dev_lh_nautical` / `prod_lh_nautical`), is declared as code (Databricks Asset Bundles) and is validated by dbt data quality tests and offline Python tests.

## Highlights

- **Infrastructure as Code:** Databricks Asset Bundles declare jobs and permissions.
- **CI/CD:** automated deployment to production with Bitbucket Pipelines.
- **Generated job YAML:** `resources/extract/generate_dab_lh_nautical.py` builds the extraction job from the table list in `config.py`.
- **Automatic retry:** `tenacity` with exponential backoff (2 s, 4 s, 8 s) on SQL Server and API calls.
- **Scheduling:** an orchestrator job chains extraction → validation → column masking → `dbt build`, running daily at 23:00.
- **Data quality:** generic dbt tests (`not_null`, `unique`, `accepted_values`) plus custom singular tests.
- **Security:** Unity Catalog column masking on sensitive fields (tax ID, email, phone, CPF) across Bronze, Silver and Gold.

## Ingestion

| Source | Technology | Load mode | Retry |
|--------|-----------|-----------|-------|
| **SQL Server (ERP)**: 24 operational tables (customers, products, sales, stock, purchases) | JDBC (`pyspark`) | Full overwrite | 3 attempts, exponential backoff |
| **PTAX API (Central Bank)**: daily USD/EUR rates | HTTP (`requests`) | Incremental (merge/upsert), with a `full` mode for historical reprocessing | 3 attempts; returns empty instead of raising |

Every Bronze table gets `_ingested_at` and `_source_path` metadata columns.

## Transformation (dbt)

| Layer | Directory | Materialization | Schema | Description |
|-------|-----------|-----------------|--------|-------------|
| **Staging** | `src/dbt/models/staging/` | `ephemeral` | n/a | Organized copy of Bronze (renamed columns, typed data) injected as CTEs |
| **Intermediate** | `src/dbt/models/intermediate/` | `table` | `silver` | Cleaning, deduplication, validation, enrichment |
| **Marts** | `src/dbt/models/marts/` | `table` | `gold` | Dimensional model (6 dimensions + 6 facts) |
| **ML** | `src/dbt/models/ml/` | `table` | `ml` | Aggregated demand, seasonality and trend index, feature table |

## Demand forecasting (ML)

**Business question:** how much will each product sell in each store over the next 3 months, and which distribution center is growing the most.

**Approach.** Demand per product × store × month has 79% of months with no sales, so the target became the **sum of the next 3 months** (50% zeros). Exploratory analysis showed that the predictable signal sits at the **category × store** level, with strong seasonality and about 15% yearly growth, while the history of a single product barely predicts its own future. That became a statistical **baseline** (category average in the store × seasonal index × trend factor) and a 33-column feature table, on which three models were compared across 12 temporal test cuts (06/2025 to 05/2026), always with a separate validation set and a single read of the test set. There are 6,054 product × store series (1,009 products × 6 locations).

| Model | Error per product × store (WAPE) | Error per category × store | Bias | Verdict |
|-------|----------------------------------|----------------------------|------|---------|
| Baseline (reference) | 86.6% | 11.9% | −2.8% | The score to beat |
| Linear Regression | 85.8% | 12.6% | −7.7% | Does not beat the baseline |
| **Poisson GLM** | 87.0% | **11.8%** | **+0.1%** | Ties on error and removes the bias: candidate model |
| Tweedie GLM (power 1.3) | 87.0% | 11.8% | −0.05% | Same as Poisson |
| Calibrated XGBoost | 85.9% | 15.6% | −10.9% | Does not beat the baseline |

**Reading:** no model reduces the error meaningfully, because what separates a product that sells 0 from one that sells 20 is not in the data before the sale. The Poisson GLM is the candidate because it matches the baseline's accuracy **without bias** and delivers the month-by-month forecast. The two models that look better per product (Linear, XGBoost) systematically forecast below actual sales.

## Document RAG

The RAG answers natural-language questions **only about the versioned technical documentation**. It does not query Bronze, Silver or Gold, does not generate SQL, and refuses questions that ask for data warehouse values.

- Dedicated schema (`dev_lh_nautical.rag`): Volume with approved documents, Delta table of chunks and a Delta Sync Hybrid index.
- Jobs: `rag_ingestion`, `rag_health_check`, `rag_evaluation` (35-case golden dataset) and `rag_demo`.
- Streamlit interface in `apps/rag_chat/`, published on Databricks Apps.

## Architecture

```
SQL Server (ERP)                PTAX API (Central Bank)
       │                              │
       ▼ ─── JDBC (full)              ▼ ─── HTTP (incremental)
┌─────────────────────────┐    ┌─────────────────────────┐
│         BRONZE          │    │         BRONZE          │
│  24 Delta Lake tables   │    │  exchange_rates Delta   │
└───────────┬─────────────┘    └───────────┬─────────────┘
            └──────────────┬───────────────┘
                           ▼ ─── dbt
                   ┌─────────────────┐
                   │     SILVER      │
                   │ staging / int.  │
                   └────────┬────────┘
                            ▼ ─── dbt
                   ┌─────────────────┐
                   │      GOLD       │
                   │      marts      │
                   └────────┬────────┘
                            ├── → Dashboards
                            ├── → Machine Learning
                            └── → Gen AI
```

## Tech stack

Databricks (Unity Catalog, Workflows, Asset Bundles) · PySpark · Delta Lake · dbt · SQL Server · Python (pandas, scikit-learn, XGBoost) · Streamlit · Bitbucket Pipelines · pytest · sqlfluff

## Quick start

Requirements: Python 3.12, Git and the Databricks CLI, with a Databricks workspace and a secret scope configured (see the [Portuguese README](README.md) for the full setup).

```bash
pip install -r requirements.txt
dbt deps
databricks bundle validate
databricks bundle deploy --target dev
databricks bundle run orchestrator_transform --target dev
```

## Project structure

```
lh_nautical/
├── databricks.yml            # main Asset Bundle config
├── dbt_project.yml           # dbt config
├── bitbucket-pipelines.yml   # CI/CD pipeline
├── resources/                # job definitions: extract, transform, orchestrator, rag, security
├── src/
│   ├── ingestion/            # SQL Server and PTAX extraction
│   ├── dbt/                  # staging, intermediate, marts, ml models
│   └── analytics_ai/         # RAG and demand forecasting code
├── notebooks/ml/             # EDA, baseline, Linear, GLM, XGBoost, growth by DC/store
├── apps/rag_chat/            # Streamlit RAG interface
├── evaluation/               # RAG golden dataset
├── docs/                     # technical documentation (Portuguese)
└── tests/                    # offline Python tests
```

## Author

Gustavo Dias de Oliveira · [LinkedIn](https://www.linkedin.com/in/gusdiaso/)
