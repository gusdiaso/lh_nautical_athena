"""Peças compartilhadas pelos notebooks de análise exploratória e de médias móveis (01 a 04).

Nomes de colunas padrão, o filtro de meses completos, o mês de referência, a
classe de frequência de venda e a correlação de Pearson segura para Spark.
Ficam aqui porque mais de um notebook usa cada uma, e nenhum notebook deve
depender do módulo de outro.
"""

from __future__ import annotations

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

DEFAULT_ID_COLS = ("sk_product", "sk_location")
DEFAULT_TARGET_COL = "demand_quantity"
DEFAULT_DATE_COL = "month_start_date"


def pearson_correlation(x: str, y: str):
    """Correlação de Pearson entre duas colunas, agregada, nula quando não há variância.

    Só entram os pares em que as duas colunas têm valor (como `F.corr`). O
    resultado é covariância ÷ (desvio × desvio), com `try_divide`: `F.corr`
    falha com divisão por zero no modo ANSI (padrão no Databricks) quando uma das
    colunas é constante — o caso de toda série sem venda —, e aqui isso dá nulo.

    Args:
        x: Nome da primeira coluna.
        y: Nome da segunda coluna.

    Returns:
        Coluna de agregação, para usar dentro de `agg`.
    """
    both = F.col(x).isNotNull() & F.col(y).isNotNull()
    x_pairs, y_pairs = F.when(both, F.col(x)), F.when(both, F.col(y))
    return F.try_divide(F.covar_pop(x_pairs, y_pairs), F.stddev_pop(x_pairs) * F.stddev_pop(y_pairs))


def add_partial_period_flag(df: DataFrame, date_col: str, grain: str) -> DataFrame:
    """Marca períodos parciais (menos dias agregados que o período do calendário).

    O período da primeira venda de cada combinação e o último período do
    dataset podem estar incompletos. O grão diário não tem períodos
    parciais nem a coluna days_in_period.

    Args:
        df: Série de demanda (weekly/monthly/quarterly com days_in_period).
        date_col: Coluna com o primeiro dia do período.
        grain: day | week | month | quarter.

    Returns:
        DataFrame com expected_days e is_partial_period.
    """
    if grain == "day":
        return df.withColumn("expected_days", F.lit(1)).withColumn(
            "is_partial_period", F.lit(False)
        )
    expected = {
        "week": F.lit(7),
        "month": F.dayofmonth(F.last_day(F.col(date_col))),
        "quarter": F.datediff(F.add_months(F.col(date_col), 3), F.col(date_col)),
    }[grain]
    return df.withColumn("expected_days", expected).withColumn(
        "is_partial_period", F.col("days_in_period") < F.col("expected_days")
    )



def complete_months(monthly: DataFrame, date_col: str = DEFAULT_DATE_COL) -> DataFrame:
    """Remove meses parciais (primeiro mês da série e último do dataset).

    Args:
        monthly: agg_demand_monthly (com days_in_period).
        date_col: Coluna com o primeiro dia do mês.

    Returns:
        DataFrame só com meses completos.
    """
    return (
        add_partial_period_flag(monthly, date_col, "month")
        .filter(~F.col("is_partial_period"))
        .drop("expected_days", "is_partial_period")
    )


def reference_month(complete: DataFrame, date_col: str = DEFAULT_DATE_COL):
    """Último mês completo do dataset — a data de referência das janelas.

    Args:
        complete: Série mensal só com meses completos.
        date_col: Coluna com o primeiro dia do mês.

    Returns:
        datetime.date do primeiro dia do mês de referência.
    """
    return complete.agg(F.max(date_col).alias("ref")).collect()[0]["ref"]


def add_frequency_class(profile: DataFrame) -> DataFrame:
    """Classe de frequência pelos meses com venda nos últimos 12 meses.

    - alta: 5 ou mais meses com venda
    - media: 3 a 4
    - baixa: 1 a 2
    - sem_venda: 0

    Os cortes seguem a distribuição destas séries (mediana de 3 meses com
    venda em 12; só ~0,2% vende em 9 meses ou mais), para que cada classe
    tenha volume suficiente para comparar. A classificação XYZ por
    coeficiente de variação não serve aqui: com ~80% de meses zerados,
    coloca quase toda série na mesma classe.
    """
    months = F.col("months_with_sale_12m")
    return profile.withColumn(
        "frequency_class",
        F.when(months >= 5, "alta")
        .when(months >= 3, "media")
        .when(months >= 1, "baixa")
        .otherwise("sem_venda"),
    )

