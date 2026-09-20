"""Testes da configuração de tabelas de ML (`ml_config`): defaults, ambiente e nomes completos."""

import dataclasses

import pytest

from src.analytics_ai.ml_config import MlFeatureConfig, MlModelConfig

ENV_VARIABLES = (
    "ML_CATALOG",
    "ML_SCHEMA",
    "GOLD_SCHEMA",
    "SILVER_SCHEMA",
    "ML_DAILY_TABLE",
    "ML_WEEKLY_TABLE",
    "ML_MONTHLY_TABLE",
    "ML_QUARTERLY_TABLE",
    "ML_FEATURES_TABLE",
    "ML_FORECAST_TABLE",
    "ML_FORECAST_MONTHLY_TABLE",
)


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    for variable in ENV_VARIABLES:
        monkeypatch.delenv(variable, raising=False)


# ── MlFeatureConfig ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("factory", "table", "date_col", "grain", "periods_per_year", "horizon"),
    [
        ("from_environment", "agg_demand_daily", "full_date", "day", 364, 91),
        ("from_environment_weekly", "agg_demand_weekly", "week_start_date", "week", 52, 13),
        ("from_environment_monthly", "agg_demand_monthly", "month_start_date", "month", 12, 3),
        ("from_environment_quarterly", "agg_demand_quarterly", "quarter_start_date", "quarter", 4, 1),
    ],
)
def test_default_grain_configuration(factory, table, date_col, grain, periods_per_year, horizon):
    config = getattr(MlFeatureConfig, factory)()
    assert config.catalog == "dev_lh_nautical"
    assert config.schema == "ml"
    assert config.gold_schema == "gold"
    assert config.silver_schema == "silver"
    assert (config.table, config.date_col, config.grain) == (table, date_col, grain)
    assert (config.periods_per_year, config.horizon_periods) == (periods_per_year, horizon)
    assert config.target_col == "demand_quantity"
    assert config.id_cols == ("sk_product", "sk_location")


def test_horizon_covers_three_months_in_every_grain():
    # Passos do grão até 3 meses: 91 dias, 13 semanas, 3 meses, 1 trimestre.
    dias_por_passo = {"day": 1, "week": 7, "month": 30.4, "quarter": 91.3}
    for config in MlFeatureConfig.all_grains().values():
        cobertura = config.horizon_periods * dias_por_passo[config.grain]
        assert 90 <= cobertura <= 92.5, config.grain


def test_periods_per_year_matches_the_grain_calendar():
    dias_por_passo = {"day": 1, "week": 7, "month": 365 / 12, "quarter": 365 / 4}
    for config in MlFeatureConfig.all_grains().values():
        ano = config.periods_per_year * dias_por_passo[config.grain]
        assert 360 <= ano <= 366, config.grain  # 364 = 52 semanas no diário: o lag cai no mesmo dia da semana


def test_qualified_names():
    config = MlFeatureConfig.from_environment_monthly()
    assert config.source_table == "dev_lh_nautical.ml.agg_demand_monthly"
    assert config.gold_table("dim_products") == "dev_lh_nautical.gold.dim_products"
    assert config.silver_table("int_high_season_months") == "dev_lh_nautical.silver.int_high_season_months"


def test_environment_overrides_every_part_of_the_name(monkeypatch):
    monkeypatch.setenv("ML_CATALOG", "prod_lh_nautical")
    monkeypatch.setenv("ML_SCHEMA", "ml_prod")
    monkeypatch.setenv("GOLD_SCHEMA", "ouro")
    monkeypatch.setenv("SILVER_SCHEMA", "prata")
    monkeypatch.setenv("ML_MONTHLY_TABLE", "minha_mensal")
    config = MlFeatureConfig.from_environment_monthly()
    assert config.source_table == "prod_lh_nautical.ml_prod.minha_mensal"
    assert config.gold_table("dim_date") == "prod_lh_nautical.ouro.dim_date"
    assert config.silver_table("x") == "prod_lh_nautical.prata.x"


def test_each_grain_reads_its_own_table_variable(monkeypatch):
    monkeypatch.setenv("ML_DAILY_TABLE", "d")
    monkeypatch.setenv("ML_WEEKLY_TABLE", "w")
    monkeypatch.setenv("ML_MONTHLY_TABLE", "m")
    monkeypatch.setenv("ML_QUARTERLY_TABLE", "q")
    tabelas = {nome: config.table for nome, config in MlFeatureConfig.all_grains().items()}
    assert tabelas == {"diario": "d", "semanal": "w", "mensal": "m", "trimestral": "q"}


def test_all_grains_order_and_keys():
    grains = MlFeatureConfig.all_grains()
    assert list(grains) == ["diario", "semanal", "mensal", "trimestral"]  # do mais fino ao mais agregado
    assert [c.grain for c in grains.values()] == ["day", "week", "month", "quarter"]


def test_feature_config_is_frozen():
    config = MlFeatureConfig.from_environment_monthly()
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.table = "outra"


def test_feature_config_reads_the_environment_at_call_time_not_import_time(monkeypatch):
    antes = MlFeatureConfig.from_environment_monthly()
    monkeypatch.setenv("ML_CATALOG", "outro_catalogo")
    depois = MlFeatureConfig.from_environment_monthly()
    assert antes.catalog == "dev_lh_nautical" and depois.catalog == "outro_catalogo"


# ── MlModelConfig ───────────────────────────────────────────────────


def test_model_config_defaults_point_to_dev_and_dbt_tables():
    config = MlModelConfig.from_environment()
    assert config.features_source == "dev_lh_nautical.ml.ml_features_produto_loja_mes"
    assert config.forecast_target == "dev_lh_nautical.ml.ml_forecast_demanda_3m"
    assert config.forecast_monthly_target == "dev_lh_nautical.ml.ml_forecast_demanda_mensal"


def test_model_config_environment_overrides(monkeypatch):
    monkeypatch.setenv("ML_CATALOG", "prod_lh_nautical")
    monkeypatch.setenv("ML_SCHEMA", "ml2")
    monkeypatch.setenv("ML_FEATURES_TABLE", "feats")
    monkeypatch.setenv("ML_FORECAST_TABLE", "f3m")
    monkeypatch.setenv("ML_FORECAST_MONTHLY_TABLE", "fmes")
    config = MlModelConfig.from_environment()
    assert config.features_source == "prod_lh_nautical.ml2.feats"
    assert config.forecast_target == "prod_lh_nautical.ml2.f3m"
    assert config.forecast_monthly_target == "prod_lh_nautical.ml2.fmes"


def test_model_config_is_frozen_and_positional_fields_are_named():
    config = MlModelConfig("c", "s", "f", "t3", "tm")
    assert (config.catalog, config.schema, config.features_table, config.forecast_table, config.forecast_monthly_table) == (
        "c", "s", "f", "t3", "tm"
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.catalog = "x"
