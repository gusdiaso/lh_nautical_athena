"""Diagnósticos de zeros em demand_quantity (Checkpoint 05 — Modelagem Preditiva).

Separa as causas por trás de um zero nas séries agg_demand_daily /
_weekly / _monthly / _quarterly — baixo giro genuíno, combinação morta
mas preenchida até o fim do dataset, e cauda longa (demanda
intermitente) — e compara os quatro grãos para escolher qual usar.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F

if TYPE_CHECKING:
    from src.analytics_ai.ml_config import MlFeatureConfig

DEFAULT_ID_COLS = ("sk_product", "sk_location")
DEFAULT_TARGET_COL = "demand_quantity"

# Cortes clássicos de Syntetos-Boylan (2005).
ADI_CUTOFF = 1.32
CV2_CUTOFF = 0.49


def _zero_flag(target_col: str):
    return F.when(F.col(target_col) == 0, 1).otherwise(0)


# ── Taxa de zero ────────────────────────────────────────────────────


def zero_rate_overall(
    df: DataFrame,
    target_col: str = DEFAULT_TARGET_COL,
    id_cols: Sequence[str] = DEFAULT_ID_COLS,
) -> DataFrame:
    """Taxa de zero do dataset inteiro.

    Args:
        df: Série de demanda densa (uma linha por combinação × período).
        target_col: Coluna de demanda.
        id_cols: Colunas que identificam a combinação.

    Returns:
        Uma linha com n_rows, n_zero_rows, zero_rate e n_combinations.
    """
    combination = F.concat_ws("|", *[F.col(c).cast("string") for c in id_cols])
    return df.agg(
        F.count("*").alias("n_rows"),
        F.sum(_zero_flag(target_col)).alias("n_zero_rows"),
        F.countDistinct(combination).alias("n_combinations"),
    ).withColumn("zero_rate", F.round(F.col("n_zero_rows") / F.col("n_rows"), 4))


def zero_rate_by(
    df: DataFrame,
    group_cols: Sequence[str],
    target_col: str = DEFAULT_TARGET_COL,
) -> DataFrame:
    """Taxa de zero por segmento.

    Args:
        df: Série de demanda com as colunas de segmentação.
        group_cols: Colunas de agrupamento (ex.: ["is_high_season"]).
        target_col: Coluna de demanda.

    Returns:
        Uma linha por segmento com n_rows, n_zero_rows, zero_rate e
        share_of_zeros (fatia do total de zeros do dataset), ordenada
        pela maior taxa de zero.
    """
    grouped = df.groupBy(*group_cols).agg(
        F.count("*").alias("n_rows"),
        F.sum(_zero_flag(target_col)).alias("n_zero_rows"),
    )
    total_zeros = Window.partitionBy()
    return (
        grouped.withColumn("zero_rate", F.round(F.col("n_zero_rows") / F.col("n_rows"), 4))
        .withColumn(
            "share_of_zeros",
            F.round(F.col("n_zero_rows") / F.sum("n_zero_rows").over(total_zeros), 4),
        )
        .orderBy(F.desc("zero_rate"))
    )


def add_segment_columns(
    df: DataFrame,
    gold_table: Callable[[str], str],
    date_col: str | None = "full_date",
) -> DataFrame:
    """Enriquece a série com colunas de segmentação da camada gold.

    agg_demand_daily/weekly só têm chaves, data e demanda. Esta função
    traz category_name (dim_products), location_type (dim_locations) e,
    no grão diário, is_high_season (dim_date).

    Args:
        df: Série de demanda.
        gold_table: Função que recebe o nome da tabela e devolve o nome
            completo em gold (ex.: MlFeatureConfig.gold_table).
        date_col: Coluna de data para juntar com dim_date; None para
            pular (grão semanal não tem correspondência com dim_date).

    Returns:
        DataFrame com as colunas de segmentação adicionadas.
    """
    spark = df.sparkSession
    products = spark.table(gold_table("dim_products")).select("sk_product", "category_name")
    locations = spark.table(gold_table("dim_locations")).select("sk_location", "location_type")

    enriched = df.join(products, "sk_product", "left").join(locations, "sk_location", "left")
    if date_col is not None:
        dates = spark.table(gold_table("dim_date")).select(
            F.col("full_date").alias(date_col), "is_high_season"
        )
        enriched = enriched.join(dates, date_col, "left")
    return enriched


# ── Cauda longa ─────────────────────────────────────────────────────


def zero_rate_by_volume_decile(
    df: DataFrame,
    id_cols: Sequence[str] = DEFAULT_ID_COLS,
    target_col: str = DEFAULT_TARGET_COL,
    n_buckets: int = 10,
) -> DataFrame:
    """Taxa de zero por decil de volume total da combinação.

    Decil 1 = combinações de menor volume (cauda longa); decil 10 = mais
    vendidas.

    Args:
        df: Série de demanda densa.
        id_cols: Colunas que identificam a combinação.
        target_col: Coluna de demanda.
        n_buckets: Número de faixas (10 = decis).

    Returns:
        Uma linha por decil com n_combinations, n_rows, n_zero_rows,
        zero_rate e total_demand.
    """
    id_cols = list(id_cols)
    volume = df.groupBy(*id_cols).agg(F.sum(target_col).alias("combination_volume"))
    deciles = volume.withColumn(
        "volume_decile", F.ntile(n_buckets).over(Window.orderBy("combination_volume"))
    )
    return (
        df.join(deciles.select(*id_cols, "volume_decile"), id_cols, "inner")
        .groupBy("volume_decile")
        .agg(
            F.countDistinct(*id_cols).alias("n_combinations"),
            F.count("*").alias("n_rows"),
            F.sum(_zero_flag(target_col)).alias("n_zero_rows"),
            F.sum(target_col).alias("total_demand"),
        )
        .withColumn("zero_rate", F.round(F.col("n_zero_rows") / F.col("n_rows"), 4))
        .orderBy("volume_decile")
    )


# ── Artefato do preenchimento global ────────────────────────────────


def zero_rows_from_trailing_dead_combinations(
    df: DataFrame,
    date_col: str,
    dead_after_days: int = 90,
    id_cols: Sequence[str] = DEFAULT_ID_COLS,
    target_col: str = DEFAULT_TARGET_COL,
) -> DataFrame:
    """Quantifica zeros vindos de combinações mortas preenchidas até o fim.

    Uma combinação é "morta" quando sua última venda aconteceu mais de
    dead_after_days antes da última data do dataset. Os zeros depois da
    última venda de uma combinação morta existem só porque o dbt expande
    toda combinação até a data máxima global.

    Args:
        df: Série de demanda densa.
        date_col: Coluna de data do grão (full_date | week_start_date).
        dead_after_days: Dias sem venda, contados até o fim do dataset,
            para considerar a combinação morta.
        id_cols: Colunas que identificam a combinação.
        target_col: Coluna de demanda.

    Returns:
        Uma linha com n_rows, n_zero_rows, n_combinations,
        n_dead_combinations, trailing_dead_zero_rows,
        trailing_dead_share_of_zeros e trailing_dead_share_of_rows.
    """
    id_cols = list(id_cols)
    dataset_end = df.agg(F.max(date_col).alias("dataset_end"))
    last_sale = df.groupBy(*id_cols).agg(
        F.max(F.when(F.col(target_col) > 0, F.col(date_col))).alias("last_sale_date")
    )
    flagged = (
        df.join(last_sale, id_cols, "inner")
        .crossJoin(dataset_end)
        .withColumn(
            "is_dead_combination",
            F.col("last_sale_date").isNull()
            | (F.datediff("dataset_end", "last_sale_date") > dead_after_days),
        )
        .withColumn(
            "is_trailing_dead_zero",
            F.col("is_dead_combination")
            & (F.col(target_col) == 0)
            & (F.col("last_sale_date").isNull() | (F.col(date_col) > F.col("last_sale_date"))),
        )
    )
    combination = F.concat_ws("|", *[F.col(c).cast("string") for c in id_cols])
    return (
        flagged.agg(
            F.count("*").alias("n_rows"),
            F.sum(_zero_flag(target_col)).alias("n_zero_rows"),
            F.countDistinct(combination).alias("n_combinations"),
            F.countDistinct(F.when(F.col("is_dead_combination"), combination)).alias(
                "n_dead_combinations"
            ),
            F.sum(F.col("is_trailing_dead_zero").cast("int")).alias("trailing_dead_zero_rows"),
        )
        .withColumn("dead_after_days", F.lit(dead_after_days))
        .withColumn(
            "trailing_dead_share_of_zeros",
            F.round(F.col("trailing_dead_zero_rows") / F.col("n_zero_rows"), 4),
        )
        .withColumn(
            "trailing_dead_share_of_rows",
            F.round(F.col("trailing_dead_zero_rows") / F.col("n_rows"), 4),
        )
    )


# ── Classificação Syntetos-Boylan ───────────────────────────────────


def demand_pattern_classification(
    df: DataFrame,
    date_col: str,
    id_cols: Sequence[str] = DEFAULT_ID_COLS,
    target_col: str = DEFAULT_TARGET_COL,
    adi_cutoff: float = ADI_CUTOFF,
    cv2_cutoff: float = CV2_CUTOFF,
) -> DataFrame:
    """Classifica cada combinação pelo padrão de demanda (Syntetos-Boylan).

    ADI = períodos da série / períodos com venda (a série é densa, então
    isso é o intervalo médio entre vendas). CV² = (desvio / média)² da
    quantidade nos períodos com venda.

    Args:
        df: Série de demanda densa.
        date_col: Coluna de data do grão.
        id_cols: Colunas que identificam a combinação.
        target_col: Coluna de demanda.
        adi_cutoff: Corte de ADI entre regular e intermitente.
        cv2_cutoff: Corte de CV² entre quantidade estável e variável.

    Returns:
        Uma linha por combinação com first_date, last_date, n_periods,
        n_nonzero_periods, n_zero_periods, adi, cv2 e demand_pattern
        (smooth | intermittent | erratic | lumpy | never_sold).
    """
    nonzero = F.when(F.col(target_col) > 0, F.col(target_col))
    stats = df.groupBy(*id_cols).agg(
        F.min(date_col).alias("first_date"),
        F.max(date_col).alias("last_date"),
        F.count("*").alias("n_periods"),
        F.count(nonzero).alias("n_nonzero_periods"),
        F.mean(nonzero).alias("mean_nonzero_demand"),
        F.stddev_pop(nonzero).alias("std_nonzero_demand"),
    )
    adi = F.col("n_periods") / F.col("n_nonzero_periods")
    cv2 = F.coalesce(
        F.pow(F.col("std_nonzero_demand") / F.col("mean_nonzero_demand"), 2), F.lit(0.0)
    )
    return (
        stats.withColumn("n_zero_periods", F.col("n_periods") - F.col("n_nonzero_periods"))
        .withColumn("adi", F.when(F.col("n_nonzero_periods") > 0, adi))
        .withColumn("cv2", F.when(F.col("n_nonzero_periods") > 0, cv2))
        .withColumn(
            "demand_pattern",
            F.when(F.col("n_nonzero_periods") == 0, "never_sold")
            .when((F.col("adi") < adi_cutoff) & (F.col("cv2") < cv2_cutoff), "smooth")
            .when((F.col("adi") >= adi_cutoff) & (F.col("cv2") < cv2_cutoff), "intermittent")
            .when((F.col("adi") < adi_cutoff) & (F.col("cv2") >= cv2_cutoff), "erratic")
            .otherwise("lumpy"),
        )
    )


def summarize_demand_patterns(patterns: DataFrame) -> DataFrame:
    """Resume a classificação de padrões de demanda.

    Args:
        patterns: Saída de demand_pattern_classification.

    Returns:
        Uma linha por padrão com n_combinations, share_of_combinations,
        n_periods, n_zero_periods, share_of_zero_periods, avg_adi e avg_cv2.
    """
    total = Window.partitionBy()
    return (
        patterns.groupBy("demand_pattern")
        .agg(
            F.count("*").alias("n_combinations"),
            F.sum("n_periods").alias("n_periods"),
            F.sum("n_zero_periods").alias("n_zero_periods"),
            F.round(F.mean("adi"), 3).alias("avg_adi"),
            F.round(F.mean("cv2"), 3).alias("avg_cv2"),
        )
        .withColumn(
            "share_of_combinations",
            F.round(F.col("n_combinations") / F.sum("n_combinations").over(total), 4),
        )
        .withColumn(
            "share_of_zero_periods",
            F.round(F.col("n_zero_periods") / F.sum("n_zero_periods").over(total), 4),
        )
        .orderBy(F.desc("n_combinations"))
    )


# ── Comparação entre grãos ──────────────────────────────────────────


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


def series_autocorrelation(
    df: DataFrame,
    date_col: str,
    lags: Sequence[int],
    id_cols: Sequence[str] = DEFAULT_ID_COLS,
    target_col: str = DEFAULT_TARGET_COL,
) -> DataFrame:
    """Autocorrelação de cada combinação nos lags pedidos.

    Mede se o passado da própria série informa o futuro — é o sinal que
    lags e médias móveis exploram num modelo. Autocorrelação perto de zero
    em todos os lags indica série sem memória: nenhum modelo baseado em
    histórico bate uma média simples.

    Args:
        df: Série de demanda densa.
        date_col: Coluna de data do grão.
        lags: Lags em períodos do grão (ex.: [1, 12] no mensal).
        id_cols: Colunas que identificam a combinação.
        target_col: Coluna de demanda.

    Returns:
        Uma linha por combinação com n_periods e acf_lag_<n> para cada lag
        (nulo quando a série é constante ou mais curta que o lag).
    """
    id_cols = list(id_cols)
    window = Window.partitionBy(*id_cols).orderBy(date_col)
    lagged = df
    for lag in lags:
        lagged = lagged.withColumn(f"_lag_{lag}", F.lag(target_col, lag).over(window))
    return lagged.groupBy(*id_cols).agg(
        F.count("*").alias("n_periods"),
        *[F.corr(target_col, f"_lag_{lag}").alias(f"acf_lag_{lag}") for lag in lags],
    )


def dispersion_index(
    df: DataFrame,
    id_cols: Sequence[str] = DEFAULT_ID_COLS,
    target_col: str = DEFAULT_TARGET_COL,
) -> DataFrame:
    """Índice de dispersão (variância / média) de cada combinação.

    Perto de 1 = contagem Poisson com taxa constante: vendas espalhadas ao
    acaso, sem picos nem padrão para um modelo aprender. Bem acima de 1 =
    sobredispersão: a demanda se concentra em alguns períodos (sazonalidade,
    rajadas, pedidos grandes), o que pode ou não ser previsível.

    Args:
        df: Série de demanda densa.
        id_cols: Colunas que identificam a combinação.
        target_col: Coluna de demanda.

    Returns:
        Uma linha por combinação com mean_demand, var_demand e dispersion.
    """
    return (
        df.groupBy(*id_cols)
        .agg(
            F.mean(target_col).alias("mean_demand"),
            F.var_pop(target_col).alias("var_demand"),
        )
        .withColumn(
            "dispersion",
            F.when(F.col("mean_demand") > 0, F.col("var_demand") / F.col("mean_demand")),
        )
    )


def grain_scorecard(
    df: DataFrame,
    grain_name: str,
    config: MlFeatureConfig,
    dead_after_days: int = 90,
) -> dict:
    """Resume em uma linha os critérios de escolha de um grão.

    Zeros, decis, séries mortas, padrão e dispersão são medidos só em
    períodos completos, para que as bordas da série não favoreçam nenhum
    grão. A autocorrelação usa a série inteira: tirar períodos parciais
    abriria buracos no tempo e deslocaria os lags.

    Args:
        df: Série de demanda do grão.
        grain_name: Rótulo do grão (ex.: "mensal").
        config: Configuração do grão (date_col, grain, periods_per_year,
            horizon_periods, id_cols, target_col).
        dead_after_days: Corte de combinação morta.

    Returns:
        Dicionário com as métricas do grão — junte vários num pandas
        DataFrame para comparar lado a lado.
    """
    date_col, target_col, id_cols = config.date_col, config.target_col, list(config.id_cols)
    flagged = add_partial_period_flag(df, date_col, config.grain)
    complete = flagged.filter(~F.col("is_partial_period"))

    base = flagged.agg(
        F.count("*").alias("n_rows"),
        F.mean(F.col("is_partial_period").cast("int")).alias("share_partial"),
    ).collect()[0]
    zeros = zero_rate_overall(complete, target_col, id_cols).collect()[0]
    n_series = zeros["n_combinations"]

    deciles = zero_rate_by_volume_decile(complete, id_cols, target_col).collect()
    dead = zero_rows_from_trailing_dead_combinations(
        complete, date_col, dead_after_days, id_cols, target_col
    ).collect()[0]

    patterns = demand_pattern_classification(complete, date_col, id_cols, target_col)
    pattern_stats = patterns.agg(
        F.percentile_approx("adi", 0.5).alias("median_adi"),
        F.mean((F.col("demand_pattern") == "smooth").cast("int")).alias("share_smooth"),
        F.mean((F.col("demand_pattern") == "lumpy").cast("int")).alias("share_lumpy"),
    ).collect()[0]

    seasonal_lag = config.periods_per_year
    acf = series_autocorrelation(flagged, date_col, [1, seasonal_lag], id_cols, target_col)
    # Autocorrelação significativa (95%) quando passa de 2/sqrt(n).
    significance = 2 / F.sqrt(F.col("n_periods"))
    acf_stats = acf.agg(
        F.percentile_approx("acf_lag_1", 0.5).alias("median_acf_lag1"),
        F.mean((F.col("acf_lag_1") > significance).cast("int")).alias("share_sig_acf_lag1"),
        F.percentile_approx(f"acf_lag_{seasonal_lag}", 0.5).alias("median_acf_seasonal"),
        F.mean((F.col(f"acf_lag_{seasonal_lag}") > significance).cast("int")).alias(
            "share_sig_acf_seasonal"
        ),
    ).collect()[0]

    dispersion = (
        dispersion_index(complete, id_cols, target_col)
        .agg(F.percentile_approx("dispersion", 0.5).alias("median_dispersion"))
        .collect()[0]
    )

    periods_per_series = base["n_rows"] / n_series
    return {
        "grao": grain_name,
        "linhas": base["n_rows"],
        "periodos_por_serie": round(periods_per_series, 1),
        "ciclos_anuais_por_serie": round(periods_per_series / config.periods_per_year, 1),
        "passos_ate_3_meses": config.horizon_periods,
        "pct_periodos_parciais": round(base["share_partial"], 4),
        "zero_rate": zeros["zero_rate"],
        "zero_rate_decil_1": deciles[0]["zero_rate"],
        "zero_rate_decil_10": deciles[-1]["zero_rate"],
        "pct_zeros_series_mortas": dead["trailing_dead_share_of_zeros"],
        "adi_mediano": round(pattern_stats["median_adi"], 2),
        "pct_smooth": round(pattern_stats["share_smooth"], 4),
        "pct_lumpy": round(pattern_stats["share_lumpy"], 4),
        "acf_lag1_mediana": _round_or_none(acf_stats["median_acf_lag1"], 3),
        "pct_series_acf_lag1_signif": round(acf_stats["share_sig_acf_lag1"], 4),
        "acf_sazonal_mediana": _round_or_none(acf_stats["median_acf_seasonal"], 3),
        "pct_series_acf_sazonal_signif": round(acf_stats["share_sig_acf_seasonal"], 4),
        "dispersao_mediana": round(dispersion["median_dispersion"], 2),
    }


def _round_or_none(value: float | None, digits: int) -> float | None:
    return None if value is None else round(value, digits)

def seasonal_signal_share(
    df: DataFrame,
    date_col: str,
    id_cols: Sequence[str] = DEFAULT_ID_COLS,
    target_col: str = DEFAULT_TARGET_COL,
) -> DataFrame:
    """Quanto da variação de cada série a sazonalidade comum explica.

    Monta um índice sazonal por mês do ano com todas as séries juntas
    (demanda média do mês / média geral) e prevê cada período como
    média da série × índice do mês. O R² compara esse ajuste com prever
    sempre a média da série:

    - R² perto de 0: o ruído domina — mesmo existindo sazonalidade no
      agregado, ela é invisível dentro da série e não dá para aprender
      com o histórico da própria série.
    - R² alto: a sazonalidade é a maior parte da variação — a série é
      previsível com atributos de calendário.

    O índice é estimado nos mesmos dados em que é avaliado, então o R² é
    um teto otimista do que a sazonalidade entrega fora da amostra.

    Args:
        df: Série de demanda densa (só períodos completos, de preferência).
        date_col: Coluna de data do grão (o mês do ano sai dela).
        id_cols: Colunas que identificam a série.
        target_col: Coluna de demanda.

    Returns:
        Uma linha com n_series, n_rows, mean_demand, r2_seasonal (agregado
        de todas as séries) e median_series_r2 (mediana por série).
    """
    id_cols = list(id_cols)
    with_month = df.withColumn("_month", F.month(date_col)).withColumn(
        "_y", F.col(target_col).cast("double")
    )
    overall_mean = with_month.agg(F.mean("_y").alias("m")).collect()[0]["m"]
    season_index = with_month.groupBy("_month").agg(
        (F.mean("_y") / F.lit(overall_mean)).alias("_season_index")
    )
    series_mean = with_month.groupBy(*id_cols).agg(F.mean("_y").alias("_series_mean"))

    fitted = (
        with_month.join(F.broadcast(season_index), "_month")
        .join(series_mean, id_cols)
        .withColumn("_fit", F.col("_series_mean") * F.col("_season_index"))
        .withColumn("_sse", F.pow(F.col("_y") - F.col("_fit"), 2))
        .withColumn("_sst", F.pow(F.col("_y") - F.col("_series_mean"), 2))
    )
    per_series = fitted.groupBy(*id_cols).agg(
        F.sum("_sse").alias("sse"), F.sum("_sst").alias("sst")
    )
    return per_series.agg(
        F.count("*").alias("n_series"),
        F.round(1 - F.sum("sse") / F.sum("sst"), 4).alias("r2_seasonal"),
        F.round(
            F.percentile_approx(F.when(F.col("sst") > 0, 1 - F.col("sse") / F.col("sst")), 0.5),
            4,
        ).alias("median_series_r2"),
    ).crossJoin(
        with_month.agg(
            F.count("*").alias("n_rows"), F.round(F.mean("_y"), 3).alias("mean_demand")
        )
    )


def aggregate_series(
    daily_segmented: DataFrame,
    id_cols: Sequence[str],
    grain: str,
    target_col: str = DEFAULT_TARGET_COL,
) -> DataFrame:
    """Reagrega a série diária num nível de série e grão de tempo quaisquer.

    Serve para testar níveis que não têm tabela no dbt, como
    categoria × loja × mês. Períodos parciais são marcados como nas
    tabelas agg_demand_* (days_in_period menor que o calendário).

    Args:
        daily_segmented: agg_demand_daily com as colunas de segmento
            (saída de add_segment_columns).
        id_cols: Colunas da nova série (ex.: ["category_name", "sk_location"]).
        grain: day | week | month | quarter.
        target_col: Coluna de demanda.

    Returns:
        DataFrame com id_cols, period_start_date, days_in_period,
        demand_quantity e is_partial_period.
    """
    id_cols = list(id_cols)
    period = (
        F.col("full_date")
        if grain == "day"
        else F.date_trunc(grain, F.col("full_date")).cast("date")
    )
    # Uma linha por série × dia antes de contar dias: várias combinações
    # produto×loja caem na mesma série agregada.
    per_day = daily_segmented.groupBy(*id_cols, "full_date").agg(
        F.sum(target_col).alias(target_col)
    )
    aggregated = per_day.groupBy(*id_cols, period.alias("period_start_date")).agg(
        F.count("*").alias("days_in_period"),
        F.sum(target_col).alias(target_col),
    )
    return add_partial_period_flag(aggregated, "period_start_date", grain)

# ── Alvo da previsão ────────────────────────────────────────────────


def horizon_target_comparison(
    complete_monthly: DataFrame,
    date_col: str = "month_start_date",
    horizon: int = 3,
    id_cols: Sequence[str] = DEFAULT_ID_COLS,
    target_col: str = DEFAULT_TARGET_COL,
) -> DataFrame:
    """Compara prever um mês isolado com prever o total dos próximos meses.

    Para cada série e mês de corte, soma a demanda dos `horizon` meses
    seguintes (só quando os `horizon` meses existem na série). Mede, para o
    mês isolado e para o total:

    - zero_rate: fração de alvos iguais a zero;
    - mean_target: valor médio do alvo;
    - median_dispersion: variância ÷ média mediana por série;
    - noise_ratio: raiz(dispersão ÷ média) — tamanho aproximado da variação
      aleatória em relação à média. É o erro que sobra mesmo com um modelo
      perfeito se as vendas chegam ao acaso (Poisson com pedidos de vários
      itens), então serve como piso de erro de cada alvo.

    Args:
        complete_monthly: Série mensal densa só com meses completos.
        date_col: Coluna com o primeiro dia do mês.
        horizon: Meses somados no alvo.
        id_cols: Colunas que identificam a série.
        target_col: Coluna de demanda.

    Returns:
        Duas linhas (um mês; total do horizonte) com n_targets, zero_rate,
        mean_target, median_dispersion e noise_ratio.
    """
    id_cols = list(id_cols)
    ahead = Window.partitionBy(*id_cols).orderBy(date_col).rowsBetween(1, horizon)
    with_total = (
        complete_monthly.withColumn("_y", F.col(target_col).cast("double"))
        .withColumn("_total", F.sum("_y").over(ahead))
        .withColumn("_months_ahead", F.count("_y").over(ahead))
        .filter(F.col("_months_ahead") == horizon)
    )
    single = complete_monthly.withColumn("_y", F.col(target_col).cast("double"))

    def summarize(df: DataFrame, value_col: str, label: str) -> DataFrame:
        per_series = df.groupBy(*id_cols).agg(
            F.mean(value_col).alias("_m"), F.var_pop(value_col).alias("_v")
        )
        dispersion = per_series.agg(
            F.percentile_approx(F.when(F.col("_m") > 0, F.col("_v") / F.col("_m")), 0.5).alias(
                "median_dispersion"
            )
        )
        overall = df.agg(
            F.count("*").alias("n_targets"),
            F.round(F.mean((F.col(value_col) == 0).cast("int")), 4).alias("zero_rate"),
            F.round(F.mean(value_col), 3).alias("mean_target"),
        )
        return (
            overall.crossJoin(dispersion)
            .withColumn("median_dispersion", F.round("median_dispersion", 2))
            .withColumn(
                "noise_ratio",
                F.round(F.sqrt(F.col("median_dispersion") / F.col("mean_target")), 2),
            )
            .select(F.lit(label).alias("alvo"), "*")
        )

    return summarize(single, "_y", "um mês").unionByName(
        summarize(with_total, "_total", f"total de {horizon} meses")
    )

# ── Definição de demanda (P2) ───────────────────────────────────────


def order_status_filter_impact(
    order_items: DataFrame,
    quantity_col: str = "quantity_ordered",
) -> DataFrame:
    """Mede quanto o filtro is_confirmed or is_paid descarta de itens de pedido.

    Args:
        order_items: fact_order_items da camada gold.
        quantity_col: Coluna de quantidade.

    Returns:
        Uma linha por order_status com included_in_demand, n_items,
        total_quantity, share_of_items e share_of_quantity. A soma de
        share_of_quantity onde included_in_demand = false é a fatia
        excluída pela definição de demanda.
    """
    total = Window.partitionBy()
    included = F.coalesce(F.col("is_confirmed"), F.lit(False)) | F.coalesce(
        F.col("is_paid"), F.lit(False)
    )
    return (
        order_items.withColumn("included_in_demand", included)
        .groupBy("order_status", "included_in_demand")
        .agg(
            F.count("*").alias("n_items"),
            F.sum(quantity_col).alias("total_quantity"),
        )
        .withColumn("share_of_items", F.round(F.col("n_items") / F.sum("n_items").over(total), 4))
        .withColumn(
            "share_of_quantity",
            F.round(F.col("total_quantity") / F.sum("total_quantity").over(total), 4),
        )
        .orderBy(F.desc("included_in_demand"), F.desc("n_items"))
    )
