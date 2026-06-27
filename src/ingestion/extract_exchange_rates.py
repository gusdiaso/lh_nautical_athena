import argparse
import time
import requests
import pandas as pd

from datetime import datetime, date, timedelta
from delta.tables import DeltaTable
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType


CURRENCIES = ["USD", "EUR"]


def parse_args():
    parser = argparse.ArgumentParser(description="Extract BCB PTAX exchange rates into Bronze")

    parser.add_argument("--catalog", default="dev_lh_nautical")
    parser.add_argument("--schema", default="bronze")
    parser.add_argument("--start-date", default="2019-07-01")

    # Estratégia de carga do pipeline:
    # - incremental: recomendado para execuções diárias.
    # - full: utilizado para carga inicial ou reprocessamento histórico.
    parser.add_argument(
        "--load-mode",
        choices=["full", "incremental"],
        default="incremental",
    )

    return parser.parse_args()


def build_spark_session():
    return SparkSession.builder.getOrCreate()


def fetch_ptax_day(currency_code: str, target_date: str) -> pd.DataFrame:
    url = (
        "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
        f"CotacaoMoedaDia(moeda=@moeda,dataCotacao=@dataCotacao)"
        f"?@moeda='{currency_code}'"
        f"&@dataCotacao='{target_date}'"
        "&$format=json"
    )

    response = requests.get(url, timeout=60)

    if response.status_code != 200:
        print(f"⚠️ Erro ao buscar {currency_code} para {target_date}: {response.status_code}")
        return pd.DataFrame()

    df = pd.DataFrame(response.json().get("value", []))

    if not df.empty:
        df["currency_code"] = currency_code

    return df


def collect_ptax_daily(currency_code: str, start_date: datetime, end_date: datetime) -> pd.DataFrame:
    dfs = []
    current_date = start_date

    while current_date <= end_date:
        api_date = current_date.strftime("%m-%d-%Y")
        df_day = fetch_ptax_day(currency_code, api_date)

        if not df_day.empty:
            dfs.append(df_day)

        current_date += timedelta(days=1)
        time.sleep(0.1)

    if dfs:
        return pd.concat(dfs, ignore_index=True)

    return pd.DataFrame()


def get_currency_start_date(spark, table_full_name: str, currency_code: str, default_start_date: datetime):
    if not spark.catalog.tableExists(table_full_name):
        return default_start_date

    last_date = (
        spark.table(table_full_name)
        .filter(F.col("currency_code") == currency_code)
        .agg(F.max("exchange_date").alias("last_date"))
        .first()["last_date"]
    )

    if last_date is None:
        return default_start_date

    return datetime.combine(last_date + timedelta(days=1), datetime.min.time())


def merge_exchange_rates(spark, df_updates, table_full_name: str):
    if not spark.catalog.tableExists(table_full_name):
        (
            df_updates.write
            .format("delta")
            .mode("overwrite")
            .option("overwriteSchema", "true")
            .saveAsTable(table_full_name)
        )
        return

    delta_table = DeltaTable.forName(spark, table_full_name)

    (
        delta_table.alias("target")
        .merge(
            df_updates.alias("source"),
            """
            target.exchange_date = source.exchange_date
            AND target.currency_code = source.currency_code
            """
        )
        .whenMatchedUpdateAll()
        .whenNotMatchedInsertAll()
        .execute()
    )


def main():
    args = parse_args()

    catalog = args.catalog
    bronze_schema = args.schema
    table_name = "exchange_rates"
    table_full_name = f"{catalog}.{bronze_schema}.{table_name}"

    default_start_date = datetime.strptime(args.start_date, "%Y-%m-%d")
    end_date = datetime.combine(date.today(), datetime.min.time())

    spark = build_spark_session()
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{bronze_schema}")

    dfs = []

    for currency_code in CURRENCIES:
        if args.load_mode == "incremental":
            start_date = get_currency_start_date(
                spark,
                table_full_name,
                currency_code,
                default_start_date,
            )
        else:
            start_date = default_start_date

        if start_date > end_date:
            print(f"✅ {currency_code} já está atualizado.")
            continue

        print(f"Buscando PTAX {currency_code} de {start_date.date()} até {end_date.date()}")
        df_currency = collect_ptax_daily(currency_code, start_date, end_date)

        if not df_currency.empty:
            dfs.append(df_currency)

    if not dfs:
        print("✅ Nenhuma nova cotação para ingerir.")
        return

    df_exchange_pd = pd.concat(dfs, ignore_index=True)
    df_exchange_raw = spark.createDataFrame(df_exchange_pd)

    df_exchange_bronze = (
        df_exchange_raw
        .select(
            F.to_date(F.col("dataHoraCotacao")).alias("exchange_date"),
            F.col("currency_code"),
            F.col("cotacaoCompra").cast(DoubleType()).alias("exchange_rate_buy"),
            F.col("cotacaoVenda").cast(DoubleType()).alias("exchange_rate_sell"),
        )
        .dropna(subset=["exchange_date", "currency_code", "exchange_rate_sell"])
        .groupBy("exchange_date", "currency_code")
        .agg(
            F.avg("exchange_rate_buy").alias("exchange_rate_buy"),
            F.avg("exchange_rate_sell").alias("exchange_rate_sell"),
        )
        .withColumn("_ingested_at", F.current_timestamp())
        .withColumn("_source_path", F.lit("api://bcb/ptax/CotacaoMoedaDia"))
    )

    if args.load_mode == "full":
        (
            df_exchange_bronze.write
            .format("delta")
            .mode("overwrite")
            .option("overwriteSchema", "true")
            .saveAsTable(table_full_name)
        )
    else:
        merge_exchange_rates(spark, df_exchange_bronze, table_full_name)

    print(f"✅ Tabela {table_full_name} atualizada com sucesso!")


if __name__ == "__main__":
    main()