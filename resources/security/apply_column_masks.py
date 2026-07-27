"""
Script para aplicar Column Masking nas tabelas Bronze, Silver e Gold
do Unity Catalog.

Pode ser executado:
  1. Localmente com Databricks Connect
  2. Como task em um job DAB no Databricks
  3. Via databricks sql execute

Uso:
  python resources/security/apply_column_masks.py [--env dev|prod] [--action apply|drop]
"""

import argparse
import os
import sys

try:
    from databricks import sql
except ImportError:
    print("databricks-sql-connector not installed. Run: pip install databricks-sql-connector")
    sys.exit(1)


MASKS = """
CREATE OR REPLACE FUNCTION {catalog}.gold.mask_full(value STRING)
  RETURN CASE
    WHEN is_member('lh_nautical_dev') THEN value
    ELSE '***MASKED***'
  END;

CREATE OR REPLACE FUNCTION {catalog}.gold.mask_cpf(value STRING)
  RETURN CASE
    WHEN is_member('lh_nautical_dev') THEN value
    ELSE '***MASKED***'
  END;

CREATE OR REPLACE FUNCTION {catalog}.gold.mask_email(value STRING)
  RETURN CASE
    WHEN is_member('lh_nautical_dev') THEN value
    ELSE '***MASKED***'
  END;

CREATE OR REPLACE FUNCTION {catalog}.gold.mask_phone(value STRING)
  RETURN CASE
    WHEN is_member('lh_nautical_dev') THEN value
    ELSE '***MASKED***'
  END;
"""

BRONZE_ALTER = """
ALTER TABLE {catalog}.bronze.customers ALTER COLUMN tax_id SET MASK {catalog}.gold.mask_full;
ALTER TABLE {catalog}.bronze.customers ALTER COLUMN email SET MASK {catalog}.gold.mask_email;
ALTER TABLE {catalog}.bronze.customers ALTER COLUMN phone SET MASK {catalog}.gold.mask_phone;
ALTER TABLE {catalog}.bronze.employees ALTER COLUMN cpf SET MASK {catalog}.gold.mask_cpf;
ALTER TABLE {catalog}.bronze.employees ALTER COLUMN email SET MASK {catalog}.gold.mask_email;
ALTER TABLE {catalog}.bronze.suppliers ALTER COLUMN tax_id SET MASK {catalog}.gold.mask_full;
ALTER TABLE {catalog}.bronze.suppliers ALTER COLUMN email SET MASK {catalog}.gold.mask_email;
ALTER TABLE {catalog}.bronze.suppliers ALTER COLUMN phone SET MASK {catalog}.gold.mask_phone;
"""

SILVER_ALTER = """
ALTER TABLE {catalog}.silver.int_customers ALTER COLUMN tax_id SET MASK {catalog}.gold.mask_full;
ALTER TABLE {catalog}.silver.int_customers ALTER COLUMN email SET MASK {catalog}.gold.mask_email;
ALTER TABLE {catalog}.silver.int_customers ALTER COLUMN phone SET MASK {catalog}.gold.mask_phone;
ALTER TABLE {catalog}.silver.int_employees ALTER COLUMN cpf SET MASK {catalog}.gold.mask_cpf;
ALTER TABLE {catalog}.silver.int_employees ALTER COLUMN email SET MASK {catalog}.gold.mask_email;
ALTER TABLE {catalog}.silver.int_suppliers ALTER COLUMN tax_id SET MASK {catalog}.gold.mask_full;
ALTER TABLE {catalog}.silver.int_suppliers ALTER COLUMN email SET MASK {catalog}.gold.mask_email;
ALTER TABLE {catalog}.silver.int_suppliers ALTER COLUMN phone SET MASK {catalog}.gold.mask_phone;
"""

GOLD_ALTER = """
ALTER TABLE {catalog}.gold.dim_customers ALTER COLUMN tax_id SET MASK {catalog}.gold.mask_full;
ALTER TABLE {catalog}.gold.dim_customers ALTER COLUMN email SET MASK {catalog}.gold.mask_email;
ALTER TABLE {catalog}.gold.dim_customers ALTER COLUMN phone SET MASK {catalog}.gold.mask_phone;
ALTER TABLE {catalog}.gold.dim_employees ALTER COLUMN cpf SET MASK {catalog}.gold.mask_cpf;
ALTER TABLE {catalog}.gold.dim_employees ALTER COLUMN email SET MASK {catalog}.gold.mask_email;
ALTER TABLE {catalog}.gold.dim_suppliers ALTER COLUMN tax_id SET MASK {catalog}.gold.mask_full;
ALTER TABLE {catalog}.gold.dim_suppliers ALTER COLUMN email SET MASK {catalog}.gold.mask_email;
ALTER TABLE {catalog}.gold.dim_suppliers ALTER COLUMN phone SET MASK {catalog}.gold.mask_phone;
"""

DROP_ALL = """
ALTER TABLE {catalog}.bronze.customers ALTER COLUMN tax_id DROP MASK;
ALTER TABLE {catalog}.bronze.customers ALTER COLUMN email DROP MASK;
ALTER TABLE {catalog}.bronze.customers ALTER COLUMN phone DROP MASK;
ALTER TABLE {catalog}.bronze.employees ALTER COLUMN cpf DROP MASK;
ALTER TABLE {catalog}.bronze.employees ALTER COLUMN email DROP MASK;
ALTER TABLE {catalog}.bronze.suppliers ALTER COLUMN tax_id DROP MASK;
ALTER TABLE {catalog}.bronze.suppliers ALTER COLUMN email DROP MASK;
ALTER TABLE {catalog}.bronze.suppliers ALTER COLUMN phone DROP MASK;
ALTER TABLE {catalog}.silver.int_customers ALTER COLUMN tax_id DROP MASK;
ALTER TABLE {catalog}.silver.int_customers ALTER COLUMN email DROP MASK;
ALTER TABLE {catalog}.silver.int_customers ALTER COLUMN phone DROP MASK;
ALTER TABLE {catalog}.silver.int_employees ALTER COLUMN cpf DROP MASK;
ALTER TABLE {catalog}.silver.int_employees ALTER COLUMN email DROP MASK;
ALTER TABLE {catalog}.silver.int_suppliers ALTER COLUMN tax_id DROP MASK;
ALTER TABLE {catalog}.silver.int_suppliers ALTER COLUMN email DROP MASK;
ALTER TABLE {catalog}.silver.int_suppliers ALTER COLUMN phone DROP MASK;
ALTER TABLE {catalog}.gold.dim_customers ALTER COLUMN tax_id DROP MASK;
ALTER TABLE {catalog}.gold.dim_customers ALTER COLUMN email DROP MASK;
ALTER TABLE {catalog}.gold.dim_customers ALTER COLUMN phone DROP MASK;
ALTER TABLE {catalog}.gold.dim_employees ALTER COLUMN cpf DROP MASK;
ALTER TABLE {catalog}.gold.dim_employees ALTER COLUMN email DROP MASK;
ALTER TABLE {catalog}.gold.dim_suppliers ALTER COLUMN tax_id DROP MASK;
ALTER TABLE {catalog}.gold.dim_suppliers ALTER COLUMN email DROP MASK;
ALTER TABLE {catalog}.gold.dim_suppliers ALTER COLUMN phone DROP MASK;
"""


def get_catalog(env: str) -> str:
    return "prod_lh_nautical" if env == "prod" else "dev_lh_nautical"


def execute_sql(statements: str, catalog: str, http_path: str, token: str):
    sql_text = statements.format(catalog=catalog)
    with sql.connect(
        server_hostname=os.environ["DATABRICKS_HOST"],
        http_path=http_path,
        access_token=token,
    ) as connection:
        with connection.cursor() as cursor:
            for statement in sql_text.strip().split(";"):
                stmt = statement.strip()
                if stmt:
                    print(f"Executing: {stmt[:80]}...")
                    cursor.execute(stmt)
                    print("  Done.")


def main():
    parser = argparse.ArgumentParser(description="Apply column masking on all layers")
    parser.add_argument("--env", default="dev", choices=["dev", "prod"])
    parser.add_argument("--action", default="apply", choices=["apply", "drop"])
    args = parser.parse_args()

    catalog = get_catalog(args.env)
    http_path = os.environ.get("DBT_HTTP_PATH")
    token = os.environ.get("DBT_DATABRICKS_TOKEN" if args.env == "dev" else "DBT_DATABRICKS_TOKEN_PROD")

    if not http_path or not token:
        print("Missing environment variables: DBT_HTTP_PATH and DBT_DATABRICKS_TOKEN[_PROD]")
        sys.exit(1)

    print(f"Target: {catalog} ({args.env})")
    print(f"Action: {args.action}")

    if args.action == "apply":
        print("Creating mask functions...")
        execute_sql(MASKS, catalog, http_path, token)

        print("Applying masks on Bronze...")
        execute_sql(BRONZE_ALTER, catalog, http_path, token)

        print("Applying masks on Silver...")
        execute_sql(SILVER_ALTER, catalog, http_path, token)

        print("Applying masks on Gold...")
        execute_sql(GOLD_ALTER, catalog, http_path, token)
    else:
        print("Dropping all masks...")
        execute_sql(DROP_ALL, catalog, http_path, token)

    print("Done.")


if __name__ == "__main__":
    main()
