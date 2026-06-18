import pandas as pd
import pyodbc

from src.ingestion.config import SOURCE_CONFIG


def get_tables_local():
    query = """
    SELECT TOP 100
        TABLE_SCHEMA,
        TABLE_NAME,
        TABLE_TYPE
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = 'dbo'
    ORDER BY TABLE_NAME;
    """

    conn_str = (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={SOURCE_CONFIG['host']},{SOURCE_CONFIG['port']};"
        f"DATABASE={SOURCE_CONFIG['database']};"
        f"UID={SOURCE_CONFIG['user']};"
        f"PWD={SOURCE_CONFIG['password']};"
        "Encrypt=yes;"
        "TrustServerCertificate=yes;"
    )

    conn = pyodbc.connect(conn_str, timeout=30)
    df = pd.read_sql(query, conn)
    conn.close()

    return df


def get_tables_databricks(spark):
    jdbc_url = (
        f"jdbc:sqlserver://{SOURCE_CONFIG['host']}:{SOURCE_CONFIG['port']};"
        f"databaseName={SOURCE_CONFIG['database']};"
        "encrypt=true;"
        "trustServerCertificate=true"
    )

    query = """
    (
        SELECT TOP 100
            TABLE_SCHEMA,
            TABLE_NAME,
            TABLE_TYPE
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = 'dbo'
        ORDER BY TABLE_NAME
    ) AS tables_list
    """

    df = (
        spark.read
        .format("jdbc")
        .option("url", jdbc_url)
        .option("dbtable", query)
        .option("user", SOURCE_CONFIG["user"])
        .option("password", SOURCE_CONFIG["password"])
        .option("driver", SOURCE_CONFIG["driver"])
        .load()
    )

    return df


def get_tables(mode="local", spark=None):
    if mode == "local":
        return get_tables_local()

    if mode == "databricks":
        if spark is None:
            raise ValueError("Para mode='databricks', passe o objeto spark.")
        return get_tables_databricks(spark)

    raise ValueError("mode deve ser 'local' ou 'databricks'.")