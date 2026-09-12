"""
Script para aplicar, revogar ou verificar o menor privilegio da identidade
do RAG documental no Unity Catalog.

A politica completa, comentada, esta em resources/security/rag_least_privilege.sql.
Este script existe para torna-la repetivel e auditavel.

Pode ser executado:
  1. Localmente com um SQL Warehouse do Databricks
  2. Como task em um job DAB no Databricks

Uso:
  python resources/security/apply_rag_grants.py --principal <application-id> --action verify
  python resources/security/apply_rag_grants.py --principal <application-id> --action apply --dry-run
  python resources/security/apply_rag_grants.py --principal <application-id> --action apply

Depois de aplicar, rode o job rag_health_check: ele prova empiricamente que a
identidade nao alcanca Bronze, Silver e Gold.
"""

import argparse
import os
import re
import sys

try:
    from databricks import sql
except ImportError:
    print("databricks-sql-connector not installed. Run: pip install databricks-sql-connector")
    sys.exit(1)


# Nomes de Service Principal (applicationId), usuario ou grupo. Restringir o
# alfabeto evita interpolar um identificador arbitrario dentro do SQL.
PRINCIPAL_PATTERN = re.compile(r"^[A-Za-z0-9._@-]+$")

WAREHOUSE_SCHEMAS = ("bronze", "silver", "gold")

DOCUMENTARY_GRANTS = """
GRANT USE CATALOG ON CATALOG {catalog} TO `{principal}`;
GRANT USE SCHEMA ON SCHEMA {catalog}.rag TO `{principal}`;
GRANT CREATE TABLE ON SCHEMA {catalog}.rag TO `{principal}`;
GRANT SELECT, MODIFY ON TABLE {catalog}.rag.document_chunks TO `{principal}`;
GRANT READ VOLUME ON VOLUME {catalog}.rag.documents TO `{principal}`;
GRANT SELECT ON TABLE {catalog}.rag.document_chunks_index TO `{principal}`;
GRANT SELECT, MODIFY ON TABLE {catalog}.rag.rag_evaluation_results TO `{principal}`;
GRANT SELECT, MODIFY ON TABLE {catalog}.rag.rag_health_checks TO `{principal}`;
"""

WAREHOUSE_ISOLATION = """
REVOKE ALL PRIVILEGES ON SCHEMA {catalog}.bronze FROM `{principal}`;
REVOKE ALL PRIVILEGES ON SCHEMA {catalog}.silver FROM `{principal}`;
REVOKE ALL PRIVILEGES ON SCHEMA {catalog}.gold FROM `{principal}`;
DENY USE SCHEMA ON SCHEMA {catalog}.bronze TO `{principal}`;
DENY USE SCHEMA ON SCHEMA {catalog}.silver TO `{principal}`;
DENY USE SCHEMA ON SCHEMA {catalog}.gold TO `{principal}`;
DENY SELECT ON SCHEMA {catalog}.bronze TO `{principal}`;
DENY SELECT ON SCHEMA {catalog}.silver TO `{principal}`;
DENY SELECT ON SCHEMA {catalog}.gold TO `{principal}`;
"""

DOCUMENTARY_REVOKES = """
REVOKE ALL PRIVILEGES ON SCHEMA {catalog}.rag FROM `{principal}`;
REVOKE ALL PRIVILEGES ON CATALOG {catalog} FROM `{principal}`;
"""

VERIFY = """
SHOW GRANTS `{principal}` ON CATALOG {catalog};
SHOW GRANTS `{principal}` ON SCHEMA {catalog}.rag;
SHOW GRANTS `{principal}` ON SCHEMA {catalog}.bronze;
SHOW GRANTS `{principal}` ON SCHEMA {catalog}.silver;
SHOW GRANTS `{principal}` ON SCHEMA {catalog}.gold;
"""


def get_catalog(env: str) -> str:
    return "prod_lh_nautical" if env == "prod" else "dev_lh_nautical"


def build_statements(template: str, catalog: str, principal: str) -> list[str]:
    text = template.format(catalog=catalog, principal=principal)
    return [statement.strip() for statement in text.split(";") if statement.strip()]


def execute(statements: list[str], http_path: str, token: str, dry_run: bool) -> None:
    if dry_run:
        for statement in statements:
            print(f"[dry-run] {statement}")
        return

    with sql.connect(
        server_hostname=os.environ["DATABRICKS_HOST"],
        http_path=http_path,
        access_token=token,
    ) as connection:
        with connection.cursor() as cursor:
            for statement in statements:
                print(f"Executing: {statement}")
                cursor.execute(statement)
                if statement.upper().startswith("SHOW GRANTS"):
                    rows = cursor.fetchall()
                    if not rows:
                        print("  (nenhum privilegio)")
                    for row in rows:
                        print(f"  {tuple(row)}")
                else:
                    print("  Done.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply least privilege for the documentary RAG identity"
    )
    parser.add_argument("--principal", required=True, help="Service Principal applicationId, user or group")
    parser.add_argument("--env", default="dev", choices=["dev", "prod"])
    parser.add_argument("--action", default="verify", choices=["apply", "revoke", "verify"])
    parser.add_argument("--dry-run", action="store_true", help="Print the statements without executing them")
    args = parser.parse_args()

    if not PRINCIPAL_PATTERN.fullmatch(args.principal):
        print("Invalid principal: use only letters, digits and . _ - @")
        sys.exit(1)

    catalog = get_catalog(args.env)
    http_path = os.environ.get("DBT_HTTP_PATH")
    token = os.environ.get("DBT_DATABRICKS_TOKEN" if args.env == "dev" else "DBT_DATABRICKS_TOKEN_PROD")

    if not args.dry_run and (not http_path or not token):
        print("Missing environment variables: DBT_HTTP_PATH and DBT_DATABRICKS_TOKEN[_PROD]")
        sys.exit(1)

    print(f"Target: {catalog} ({args.env})")
    print(f"Principal: {args.principal}")
    print(f"Action: {args.action}")

    if args.action == "apply":
        statements = build_statements(DOCUMENTARY_GRANTS, catalog, args.principal)
        statements += build_statements(WAREHOUSE_ISOLATION, catalog, args.principal)
    elif args.action == "revoke":
        statements = build_statements(DOCUMENTARY_REVOKES, catalog, args.principal)
    else:
        statements = build_statements(VERIFY, catalog, args.principal)

    execute(statements, http_path, token, args.dry_run)
    print("Done.")


if __name__ == "__main__":
    main()
