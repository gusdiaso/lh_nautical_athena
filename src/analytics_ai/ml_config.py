"""Configuração de ambiente das tabelas de apoio a Machine Learning (schema ml)."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class MlFeatureConfig:
    """Nomes validados das tabelas de demanda usadas na Modelagem Preditiva.

    Attributes:
        catalog: Catálogo Unity Catalog (dev_lh_nautical | prod_lh_nautical).
        schema: Schema das tabelas de ML materializadas pelo dbt.
        gold_schema: Schema da camada gold (dimensões e fatos).
        silver_schema: Schema da camada silver (intermediate).
        table: Nome da tabela de demanda (agg_demand_daily | _weekly | _monthly | _quarterly).
        date_col: Coluna de data do grão da tabela.
        grain: Nome do grão (day | week | month | quarter).
        periods_per_year: Períodos do grão em um ano — lag sazonal anual.
        horizon_periods: Períodos do grão que cobrem o horizonte de 3 meses.
        target_col: Coluna alvo de demanda.
        id_cols: Colunas que identificam a série (produto × loja).
    """

    catalog: str
    schema: str
    gold_schema: str
    silver_schema: str
    table: str
    date_col: str
    grain: str
    periods_per_year: int
    horizon_periods: int
    target_col: str = "demand_quantity"
    id_cols: tuple[str, ...] = ("sk_product", "sk_location")

    @property
    def source_table(self) -> str:
        """Nome completo da tabela de demanda (catalog.schema.table)."""
        return f"{self.catalog}.{self.schema}.{self.table}"

    def gold_table(self, name: str) -> str:
        """Nome completo de uma tabela da camada gold.

        Args:
            name: Nome da tabela em gold (ex.: dim_products).

        Returns:
            Nome no formato catalog.gold_schema.name.
        """
        return f"{self.catalog}.{self.gold_schema}.{name}"

    def silver_table(self, name: str) -> str:
        """Nome completo de uma tabela da camada silver.

        Args:
            name: Nome da tabela em silver (ex.: int_high_season_months).

        Returns:
            Nome no formato catalog.silver_schema.name.
        """
        return f"{self.catalog}.{self.silver_schema}.{name}"

    @classmethod
    def _from_environment(
        cls,
        table_env: str,
        table_default: str,
        date_col: str,
        grain: str,
        periods_per_year: int,
        horizon_periods: int,
    ) -> MlFeatureConfig:
        return cls(
            catalog=os.getenv("ML_CATALOG", "dev_lh_nautical"),
            schema=os.getenv("ML_SCHEMA", "ml"),
            gold_schema=os.getenv("GOLD_SCHEMA", "gold"),
            silver_schema=os.getenv("SILVER_SCHEMA", "silver"),
            table=os.getenv(table_env, table_default),
            date_col=date_col,
            grain=grain,
            periods_per_year=periods_per_year,
            horizon_periods=horizon_periods,
        )

    @classmethod
    def from_environment(cls) -> MlFeatureConfig:
        """Configuração do grão diário (agg_demand_daily)."""
        # 364 = 52 semanas: o lag anual cai no mesmo dia da semana.
        return cls._from_environment(
            "ML_DAILY_TABLE", "agg_demand_daily", "full_date", "day", 364, 91
        )

    @classmethod
    def from_environment_weekly(cls) -> MlFeatureConfig:
        """Configuração do grão semanal (agg_demand_weekly)."""
        return cls._from_environment(
            "ML_WEEKLY_TABLE", "agg_demand_weekly", "week_start_date", "week", 52, 13
        )

    @classmethod
    def from_environment_monthly(cls) -> MlFeatureConfig:
        """Configuração do grão mensal (agg_demand_monthly)."""
        return cls._from_environment(
            "ML_MONTHLY_TABLE", "agg_demand_monthly", "month_start_date", "month", 12, 3
        )

    @classmethod
    def from_environment_quarterly(cls) -> MlFeatureConfig:
        """Configuração do grão trimestral (agg_demand_quarterly)."""
        return cls._from_environment(
            "ML_QUARTERLY_TABLE", "agg_demand_quarterly", "quarter_start_date", "quarter", 4, 1
        )

    @classmethod
    def all_grains(cls) -> dict[str, MlFeatureConfig]:
        """Configurações dos quatro grãos, do mais fino ao mais agregado."""
        return {
            "diario": cls.from_environment(),
            "semanal": cls.from_environment_weekly(),
            "mensal": cls.from_environment_monthly(),
            "trimestral": cls.from_environment_quarterly(),
        }
