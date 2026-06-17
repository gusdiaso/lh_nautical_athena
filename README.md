# LH Nautical - Group 5

Data Engineering project for LH Nautical, developed using Databricks, Python/PySpark, dbt, and a Medallion Lakehouse architecture.

## Project Structure

```text
grupo_5/
├── dbt/
├── docs/
├── notebooks/
├── resources/
│   └── sql/
├── src/
│   └── ingestion/
├── tests/
├── databricks.yml
├── pyproject.toml
└── README.md
```

## Architecture

The project follows a Medallion Architecture:

```text
Raw
↓
Bronze
↓
Silver
↓
Gold
```

### Databricks Environments

```text
dev_lh_nautical
├── raw
├── bronze
├── silver
└── gold

prod_lh_nautical
├── raw
├── bronze
├── silver
└── gold
```

## Data Source

The primary data source is a SQL Server database.

- Local exploration and validation: `pyodbc`
- Official ingestion pipeline: Spark + JDBC on Databricks

---

# Local Environment Setup

## 1. Clone the Repository

```bash
git clone git@bitbucket.org:indiciumtech/grupo_5.git

cd grupo_5
```

## 2. Create and Activate a Virtual Environment

```bash
python3 -m venv .venv

source .venv/bin/activate
```

Validate:

```bash
which python
```

Expected result:

```text
.../grupo_5/.venv/bin/python
```

---

## 3. Install Python Dependencies

```bash
pip install -r requirements.txt
```

If notebooks do not execute properly in VS Code:

```bash
pip install ipykernel
```

---

## 4. Install SQL Server ODBC Dependencies (macOS)

Install UnixODBC:

```bash
brew install unixodbc
```

Add Microsoft's repository:

```bash
brew tap microsoft/mssql-release https://github.com/Microsoft/homebrew-mssql-release
```

Trust the repository:

```bash
brew trust microsoft/mssql-release
```

Install the SQL Server driver:

```bash
ACCEPT_EULA=Y brew install msodbcsql18
```

---

## 5. Reinstall pyodbc

After installing the drivers:

```bash
source .venv/bin/activate

pip uninstall pyodbc -y

pip install pyodbc
```

---

## 6. Validate SQL Server Driver Installation

Open a Python notebook and run:

```python
import pyodbc

print(pyodbc.drivers())
```

Expected result:

```text
['ODBC Driver 18 for SQL Server']
```

---

# Local Configuration Setup

The repository includes a configuration template:

```text
src/ingestion/config_example.py
```

Before running any notebook or ingestion script, create your local configuration file:

```bash
cp src/ingestion/config_example.py src/ingestion/config.py
```

Update the password field in `src/ingestion/config.py`:

```python
SOURCE_CONFIG = {
    "host": "18.209.218.63",
    "port": 4563,
    "database": "lh_nautical",
    "schema": "dbo",
    "user": "student",
    "password": "<YOUR_PASSWORD>",
    "driver": "com.microsoft.sqlserver.jdbc.SQLServerDriver",
}

TARGET_CONFIG = {
    "dev_catalog": "dev_lh_nautical",
    "prod_catalog": "prod_lh_nautical",
    "raw_schema": "raw",
    "bronze_schema": "bronze",
    "silver_schema": "silver",
    "gold_schema": "gold",
}
```

## Important

The file:

```text
src/ingestion/config.py
```

is ignored by Git and must never be committed.

Only the template file:

```text
src/ingestion/config_example.py
```

is versioned in the repository.

This approach keeps credentials secure while maintaining a standardized project configuration across the team.

---

## Before Running the Notebooks

Make sure you have created your local configuration file:

```bash
cp src/ingestion/config_example.py src/ingestion/config.py
```

and updated the database password before executing:

```text
notebooks/01_test_sqlserver_connection.ipynb
```

---

# Local Connection Test

Run:

```text
notebooks/01_test_sqlserver_connection.ipynb
```

Purpose:

- Validate SQL Server connectivity
- List available tables in the `dbo` schema
- Explore the LH Nautical source database

---

# Databricks Environment Setup

Run:

```text
resources/sql/01_create_environment.sql
```

This script creates:

```text
dev_lh_nautical.raw
dev_lh_nautical.bronze
dev_lh_nautical.silver
dev_lh_nautical.gold

prod_lh_nautical.raw
prod_lh_nautical.bronze
prod_lh_nautical.silver
prod_lh_nautical.gold
```

---

# Databricks Bundle

Validate the bundle:

```bash
databricks bundle validate --profile lh-nautical-developers
```

Deploy to DEV:

```bash
databricks bundle deploy --target dev --profile lh-nautical-developers
```

Deploy to PROD:

```bash
databricks bundle deploy --target prod --profile lh-nautical-developers
```

---

# Notes

- Local testing uses `pyodbc` only for source exploration and connectivity validation.
- The official ingestion pipeline will be developed under `src/ingestion/`.
- Production ingestion will use Spark/JDBC and run on Databricks.
- Notebooks inside the `notebooks/` directory are intended for testing, exploration, and validation purposes.