"""Executa o primeiro XGBoost sobre as features dbt já validadas."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from src.analytics_ai.demand_xgboost import load_panel, run


def create_spark_session():
    """Usa Spark do Runtime no Databricks e Connect fora dele."""
    if os.getenv("DATABRICKS_RUNTIME_VERSION"):
        from pyspark.sql import SparkSession

        return SparkSession.builder.getOrCreate()

    from src.ingestion.utils import build_spark_session

    return build_spark_session()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-output", default="previsoes_teste_xgboost_offset_duas_etapas.csv", help="CSV com previsões nos cortes de teste")
    parser.add_argument("--forecast-output", default="previsoes_atuais_xgboost_offset_duas_etapas.csv", help="CSV com previsões do corte mais recente")
    parser.add_argument("--metrics-output", default="metricas_xgboost_offset_duas_etapas.csv", help="CSV com métricas de validação e teste")
    parser.add_argument("--search-output", default="busca_validacao_xgboost_offset_duas_etapas.csv", help="CSV das buscas na validação")
    args = parser.parse_args()
    original_files = {Path(name).resolve() for name in (
        "previsoes_teste.csv", "previsoes_atuais.csv", "previsoes_teste_calibradas.csv",
        "previsoes_atuais_calibradas.csv", "comparacao_calibracao_validacao.csv",
    )}
    outputs = (args.test_output, args.forecast_output, args.metrics_output, args.search_output)
    if any(Path(path).resolve() in original_files for path in outputs) or len({Path(path).resolve() for path in outputs}) != 4:
        parser.error("Use quatro nomes distintos que preservem os CSVs existentes")

    result = run(load_panel(create_spark_session()))
    split = result["split"]
    print(f"Validação: {split.validation_cutoffs[0]} a {split.validation_cutoffs[-1]}")
    print(f"Teste: {split.test_cutoffs[0]} a {split.test_cutoffs[-1]}")
    chosen = result["calibration"]
    print(f"Parâmetros escolhidos: {result['best_parameters']}")
    print(f"Escolha na validação: {chosen.name}; peso XGBoost={chosen.xgb_weight:.0%}; fator={chosen.multiplier:.4f}")
    print(f"Deslocamento residual log escolhido: {result['residual_shift']:.6f}")
    print(f"Base margin: epsilon={result['base_margin_search'].iloc[0]['epsilon']:.1e}")
    print(f"Conjunto escolhido na validação: {result['selected_feature_set']}")
    print("\nConjuntos de features na validação (menor pontuação vence):")
    print(result["feature_search"].to_string(index=False, float_format=lambda value: f"{value:.4f}"))
    print("\nValidação (WAPE e viés em fração):")
    print(result["validation_metrics"].to_string(float_format=lambda value: f"{value:.4f}"))
    print("\nBaselines selecionadas na validação:")
    print(result["baseline_ranking"].to_string(index=False, float_format=lambda value: f"{value:.4f}"))
    print("\nTeste (WAPE e viés em fração):")
    print(result["test_metrics"].to_string(float_format=lambda value: f"{value:.4f}"))
    print("\nTeste por corte:")
    print(result["test_metrics_by_cutoff"].to_string(float_format=lambda value: f"{value:.4f}"))
    forecast = result["future_predictions"]
    print(f"\nCorte de inferência: {forecast['cutoff'].iloc[0]}; previsões: {len(forecast)}")
    print("\nClassificação duas etapas:")
    print(result["two_stage_classification"].head(1).to_string(index=False, float_format=lambda value: f"{value:.4f}"))
    import pandas as pd
    searches = [result["base_margin_search"].assign(experimento="base_margin"),
                result["two_stage_search"].assign(experimento="duas_etapas"),
                result["residual_search"].assign(experimento="residual")]
    pd.concat(searches, ignore_index=True, sort=False).to_csv(args.search_output, index=False)
    validation_metrics = result["validation_metrics"].reset_index().assign(particao="validacao")
    test_metrics = result["test_metrics"].reset_index().assign(particao="teste")
    pd.concat([validation_metrics, test_metrics], ignore_index=True).to_csv(args.metrics_output, index=False)
    result["test_predictions"].to_csv(args.test_output, index=False)
    forecast.to_csv(args.forecast_output, index=False)


if __name__ == "__main__":
    main()
