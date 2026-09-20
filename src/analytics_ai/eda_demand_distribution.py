"""Distribuição das séries de demanda produto × loja (Etapa 1 do plano de previsão).

Classifica cada série por concentração de volume (ABC), frequência de venda
e fase de vida, e mede sazonalidade por categoria, tendência e alcance dos
produtos. Tudo parte de agg_demand_monthly, só com meses completos, e usa
um mês de referência (o último mês completo do dataset) para as janelas de
12 meses.
"""

from __future__ import annotations

from collections.abc import Sequence

from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F

from src.analytics_ai.eda_common import (
    DEFAULT_DATE_COL,
    DEFAULT_ID_COLS,
    DEFAULT_TARGET_COL,
    complete_months,
    pearson_correlation,
)

# Limites da curva ABC: A = séries que somam os primeiros 80% do volume,
# B = os 15% seguintes, C = os 5% finais.
ABC_A_SHARE = 0.80
ABC_B_SHARE = 0.95

# Uma série precisa de 12 meses de histórico para a média de 12 meses (MM12),
# a baseline principal da Etapa 2.
MIN_HISTORY_MONTHS = 12


# ── Base ────────────────────────────────────────────────────────────


def _window_filter(date_col: str, ref_month, start_offset: int, end_offset: int):
    """Filtro de meses entre ref - start_offset e ref - end_offset (inclusive)."""
    ref = F.lit(ref_month).cast("date")
    return (F.col(date_col) >= F.add_months(ref, -start_offset)) & (
        F.col(date_col) <= F.add_months(ref, -end_offset)
    )


# ── Estatísticas por série ──────────────────────────────────────────


def series_profile(
    monthly: DataFrame,
    ref_month,
    date_col: str = DEFAULT_DATE_COL,
    id_cols: Sequence[str] = DEFAULT_ID_COLS,
    target_col: str = DEFAULT_TARGET_COL,
) -> DataFrame:
    """Perfil de cada série produto × loja no mês de referência.

    A primeira e a última venda usam a série inteira (inclusive meses
    parciais, onde a primeira venda sempre cai). As métricas de 12 meses
    usam só meses completos entre ref-11 e ref.

    Args:
        monthly: agg_demand_monthly inteira (com meses parciais).
        ref_month: Mês de referência (saída de reference_month).
        date_col: Coluna com o primeiro dia do mês.
        id_cols: Colunas que identificam a série.
        target_col: Coluna de demanda.

    Returns:
        Uma linha por série com first_sale_month, last_sale_month,
        history_months, months_since_last_sale, volume_12m,
        months_with_sale_12m e mean_12m (volume ÷ 12: meses em que a série
        ainda não existia contam como zero).
    """
    id_cols = list(id_cols)
    ref = F.lit(ref_month).cast("date")
    lifetime = (
        monthly.filter(F.col(date_col) <= ref)
        .groupBy(*id_cols)
        .agg(
            F.min(F.when(F.col(target_col) > 0, F.col(date_col))).alias("first_sale_month"),
            F.max(F.when(F.col(target_col) > 0, F.col(date_col))).alias("last_sale_month"),
        )
        .withColumn(
            "history_months",
            F.months_between(ref, F.col("first_sale_month")).cast("int") + 1,
        )
        .withColumn(
            "months_since_last_sale",
            F.months_between(ref, F.col("last_sale_month")).cast("int"),
        )
    )
    last_12 = (
        complete_months(monthly, date_col)
        .filter(_window_filter(date_col, ref_month, 11, 0))
        .groupBy(*id_cols)
        .agg(
            F.sum(target_col).cast("double").alias("volume_12m"),
            F.sum((F.col(target_col) > 0).cast("int")).alias("months_with_sale_12m"),
        )
        .withColumn("mean_12m", F.col("volume_12m") / F.lit(12))
    )
    return (
        lifetime.join(last_12, id_cols, "left")
        .fillna({"volume_12m": 0.0, "months_with_sale_12m": 0, "mean_12m": 0.0})
        .filter(F.col("first_sale_month").isNotNull())
    )


def add_abc_class(
    profile: DataFrame,
    value_col: str = "volume_12m",
    a_share: float = ABC_A_SHARE,
    b_share: float = ABC_B_SHARE,
) -> DataFrame:
    """Classe ABC de cada série pelo volume acumulado.

    Ordena as séries do maior para o menor volume e acumula a fatia do
    volume total: A até a_share, B até b_share, C o resto. Séries sem
    volume na janela ficam como "sem_venda".

    Args:
        profile: Saída de series_profile.
        value_col: Coluna de volume.
        a_share: Fatia acumulada que fecha a classe A.
        b_share: Fatia acumulada que fecha a classe B.

    Returns:
        DataFrame com cumulative_share e abc_class.
    """
    ordered = Window.orderBy(F.desc(value_col)).rowsBetween(Window.unboundedPreceding, 0)
    total = profile.agg(F.sum(value_col).alias("t")).collect()[0]["t"]
    # Sem volume nenhum (tabela vazia ou tudo zero) a fatia não existe: nula, e
    # todas as séries caem em "sem_venda" — em vez de dividir por zero.
    denominator = F.lit(total) if total else F.lit(None).cast("double")
    cumulative = F.sum(value_col).over(ordered) / denominator
    # A série entra na classe em que o volume acumulado ANTES dela ainda cabia.
    previous = cumulative - F.col(value_col) / denominator
    return profile.withColumn("cumulative_share", cumulative).withColumn(
        "abc_class",
        F.when(F.col(value_col) <= 0, "sem_venda")
        .when(previous < a_share, "A")
        .when(previous < b_share, "B")
        .otherwise("C"),
    )


def add_life_phase(profile: DataFrame, min_history: int = MIN_HISTORY_MONTHS) -> DataFrame:
    """Fase de vida da série no mês de referência.

    - parada: sem venda nos últimos 12 meses
    - nova: primeira venda há menos de min_history meses (a MM12 não fecha)
    - ativa: o resto

    Args:
        profile: Saída de series_profile.
        min_history: Meses de histórico para deixar de ser nova.
    """
    return profile.withColumn(
        "life_phase",
        F.when(F.col("months_since_last_sale") >= 12, "parada")
        .when(F.col("history_months") < min_history, "nova")
        .otherwise("ativa"),
    )


def segment_summary(segmented: DataFrame, group_cols: Sequence[str]) -> DataFrame:
    """Séries e volume por segmento.

    Args:
        segmented: Perfil com as classes (abc_class, frequency_class, life_phase).
        group_cols: Colunas de segmento.

    Returns:
        Uma linha por segmento com n_series, share_series, volume_12m e
        share_volume_12m.
    """
    total = Window.partitionBy()
    return (
        segmented.groupBy(*group_cols)
        .agg(F.count("*").alias("n_series"), F.sum("volume_12m").alias("volume_12m"))
        .withColumn(
            "share_series", F.round(F.try_divide(F.col("n_series"), F.sum("n_series").over(total)), 4)
        )
        .withColumn(
            "share_volume_12m",
            F.round(F.try_divide(F.col("volume_12m"), F.sum("volume_12m").over(total)), 4),
        )
        .orderBy(*group_cols)
    )


def pareto_points(
    profile: DataFrame,
    value_col: str = "volume_12m",
    series_shares: Sequence[float] = (0.05, 0.10, 0.20, 0.50),
) -> DataFrame:
    """Fatia do volume nas séries que mais vendem.

    Args:
        profile: Perfil das séries.
        value_col: Coluna de volume.
        series_shares: Fatias do topo das séries a medir (0,2 = top 20%).

    Returns:
        Uma linha por fatia com top_share_series e share_volume.
    """
    ranked = profile.withColumn("_rank", F.row_number().over(Window.orderBy(F.desc(value_col))))
    stats = ranked.agg(F.count("*").alias("n"), F.sum(value_col).alias("total")).collect()[0]
    if not stats["total"]:
        raise ValueError("perfil vazio ou sem volume: não há concentração para medir")
    rows = []
    for share in series_shares:
        top_n = max(1, int(round(stats["n"] * share)))
        volume = ranked.filter(F.col("_rank") <= top_n).agg(F.sum(value_col)).collect()[0][0]
        rows.append((float(share), top_n, round(float(volume) / float(stats["total"]), 4)))
    return profile.sparkSession.createDataFrame(
        rows, "top_share_series double, top_n_series int, share_volume double"
    )


# ── Sazonalidade, tendência e alcance ───────────────────────────────


def seasonal_index_by(
    complete: DataFrame,
    group_cols: Sequence[str],
    date_col: str = DEFAULT_DATE_COL,
    target_col: str = DEFAULT_TARGET_COL,
) -> DataFrame:
    """Índice sazonal por grupo (ex.: categoria) com a regra da alta temporada.

    Mesma regra de int_high_season_months, aplicada dentro de cada grupo:
    demanda total do grupo por mês, média por mês do ano, dividida pela
    média das 12 médias mensais do grupo.

    Args:
        complete: Série mensal só com meses completos e as colunas de grupo.
        group_cols: Colunas de agrupamento.
        date_col: Coluna com o primeiro dia do mês.
        target_col: Coluna de demanda.

    Returns:
        Uma linha por grupo × mês do ano com avg_monthly_demand,
        seasonal_index e is_high_season.
    """
    group_cols = list(group_cols)
    monthly_total = complete.groupBy(*group_cols, date_col).agg(
        F.sum(F.col(target_col).cast("double")).alias("_q")
    )
    by_month = monthly_total.groupBy(*group_cols, F.month(date_col).alias("month_number")).agg(
        F.mean("_q").alias("avg_monthly_demand")
    )
    group_mean = Window.partitionBy(*group_cols)
    return (
        by_month.withColumn(
            "seasonal_index",
            F.round(F.try_divide(F.col("avg_monthly_demand"), F.mean("avg_monthly_demand").over(group_mean)), 4),
        )
        .withColumn("is_high_season", F.col("seasonal_index") > 1)
        .orderBy(*group_cols, "month_number")
    )


def compare_to_global_season(by_group: DataFrame, global_season: DataFrame, group_col: str) -> DataFrame:
    """Compara o índice sazonal de cada grupo com o índice geral.

    Args:
        by_group: Saída de seasonal_index_by com uma coluna de grupo.
        global_season: int_high_season_months (month_number, seasonal_index,
            is_high_season).
        group_col: Coluna de grupo.

    Returns:
        Uma linha por grupo com correlation_with_global (1 = mesmo formato
        de padrão sazonal), max_abs_diff (maior distância de índice num mês),
        peak_month, high_season_months e months_differing_from_global
        (meses em que a classificação alta/baixa discorda da geral).
    """
    joined = by_group.join(
        global_season.select(
            "month_number",
            F.col("seasonal_index").alias("global_index"),
            F.col("is_high_season").alias("global_high_season"),
        ),
        "month_number",
    )
    peak = Window.partitionBy(group_col).orderBy(F.desc("seasonal_index"))
    return (
        joined.withColumn("_rank", F.row_number().over(peak))
        .groupBy(group_col)
        .agg(
            F.round(pearson_correlation("seasonal_index", "global_index"), 3).alias("correlation_with_global"),
            F.round(F.max(F.abs(F.col("seasonal_index") - F.col("global_index"))), 3).alias(
                "max_abs_diff"
            ),
            F.max(F.when(F.col("_rank") == 1, F.col("month_number"))).alias("peak_month"),
            F.concat_ws(
                ",",
                F.array_sort(
                    F.collect_list(F.when(F.col("is_high_season"), F.col("month_number")))
                ).cast("array<string>"),
            ).alias("high_season_months"),
            F.sum((F.col("is_high_season") != F.col("global_high_season")).cast("int")).alias(
                "months_differing_from_global"
            ),
        )
        .orderBy("correlation_with_global")
    )


def year_over_year_growth(
    complete: DataFrame,
    ref_month,
    group_cols: Sequence[str] = (),
    date_col: str = DEFAULT_DATE_COL,
    target_col: str = DEFAULT_TARGET_COL,
    id_cols: Sequence[str] = DEFAULT_ID_COLS,
) -> DataFrame:
    """Crescimento dos últimos 12 meses contra os 12 anteriores.

    Mostra também quantas séries venderam em cada janela: crescimento que
    vem só de mais séries ativas não é o mesmo que cada produto vender mais.

    Args:
        complete: Série mensal só com meses completos.
        ref_month: Mês de referência.
        group_cols: Colunas de agrupamento; vazio = total geral.
        date_col: Coluna com o primeiro dia do mês.
        target_col: Coluna de demanda.
        id_cols: Colunas que identificam a série.

    Returns:
        Uma linha por grupo com volume_prev_12m, volume_last_12m,
        growth, series_selling_prev_12m e series_selling_last_12m.
    """
    group_cols = list(group_cols)
    series_key = F.concat_ws("|", *[F.col(c).cast("string") for c in id_cols])
    last = _window_filter(date_col, ref_month, 11, 0)
    prev = _window_filter(date_col, ref_month, 23, 12)
    selling = F.col(target_col) > 0
    grouped = complete.groupBy(*group_cols) if group_cols else complete.groupBy()
    return grouped.agg(
        # Grupo sem linha na janela = volume 0 (e não nulo), para o crescimento poder ser -100%.
        F.coalesce(F.sum(F.when(prev, F.col(target_col))), F.lit(0)).cast("double").alias("volume_prev_12m"),
        F.coalesce(F.sum(F.when(last, F.col(target_col))), F.lit(0)).cast("double").alias("volume_last_12m"),
        F.countDistinct(F.when(prev & selling, series_key)).alias("series_selling_prev_12m"),
        F.countDistinct(F.when(last & selling, series_key)).alias("series_selling_last_12m"),
    ).withColumn(
        # Sem volume no ano anterior o crescimento é indefinido (nulo), não um erro.
        "growth",
        F.round(F.try_divide(F.col("volume_last_12m"), F.col("volume_prev_12m")) - 1, 4),
    )


def product_reach(
    profile: DataFrame,
    product_col: str = "sk_product",
    location_col: str = "sk_location",
) -> DataFrame:
    """Em quantas lojas cada produto vendeu nos últimos 12 meses.

    Args:
        profile: Perfil das séries (com volume_12m).
        product_col: Coluna do produto.
        location_col: Coluna da loja.

    Returns:
        Uma linha por quantidade de lojas com n_products, share_products e
        share_volume_12m.
    """
    per_product = (
        profile.filter(F.col("volume_12m") > 0)
        .groupBy(product_col)
        .agg(
            F.countDistinct(location_col).alias("locations_selling_12m"),
            F.sum("volume_12m").alias("volume_12m"),
        )
    )
    total = Window.partitionBy()
    return (
        per_product.groupBy("locations_selling_12m")
        .agg(F.count("*").alias("n_products"), F.sum("volume_12m").alias("volume_12m"))
        .withColumn(
            "share_products", F.round(F.col("n_products") / F.sum("n_products").over(total), 4)
        )
        .withColumn(
            "share_volume_12m", F.round(F.col("volume_12m") / F.sum("volume_12m").over(total), 4)
        )
        .orderBy("locations_selling_12m")
    )
