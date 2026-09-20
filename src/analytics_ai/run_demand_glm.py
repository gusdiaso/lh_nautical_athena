"""Treina o GLM de demanda e grava as previsões no Unity Catalog.

Segue o padrão de import dos demais módulos de ML (`src.analytics_ai...`), por
isso roda como módulo a partir da raiz do repositório:

    PYTHONPATH=. python -m src.analytics_ai.run_demand_glm --model-name glm_poisson

Por padrão treina nas linhas anteriores à validação e grava o teste e a
inferência. Para produzir a previsão de verdade com todo o histórico
disponível, use `--fit-on completo`, que treina em todos os cortes com alvo
conhecido — as métricas publicadas, porém, vêm sempre de `--fit-on treino`,
porque só aí o teste permanece intocado.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt

import pandas as pd

from src.analytics_ai.demand_common import comparison_scorecard
from src.analytics_ai.demand_glm import (
    BASELINE_COL,
    FEATURE_STEPS,
    add_predictions,
    decompose_months,
    fit_glm,
    split_panel,
)
from src.analytics_ai.demand_predictions import (
    build_forecast_3m_frame,
    build_forecast_mensal_frame,
    read_features,
    write_forecast_3m,
    write_forecast_mensal,
)
from src.analytics_ai.ml_config import MlModelConfig
from src.ingestion.utils import build_spark_session


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Interpreta os argumentos da linha de comando."""
    parser = argparse.ArgumentParser(description="Treina o GLM de demanda e grava as previsões.")
    parser.add_argument("--model-name", default="glm_poisson", help="Rótulo e partição do modelo.")
    parser.add_argument("--step", default="passo3_historico", choices=sorted(FEATURE_STEPS))
    parser.add_argument("--family", default="poisson", choices=("poisson", "tweedie"))
    parser.add_argument("--power", type=float, default=1.3, help="Potência do Tweedie.")
    parser.add_argument("--alpha", type=float, default=0.0, help="Regularização L2.")
    parser.add_argument(
        "--fit-on",
        default="treino",
        choices=("treino", "completo"),
        help="treino = só o recorte de treino (métricas válidas); completo = todo alvo conhecido.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Calcula e imprime, sem gravar.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Executa o pipeline completo: ler, treinar, prever, gravar."""
    args = parse_args(argv)
    config = MlModelConfig.from_environment()
    spark = build_spark_session()
    print(f"lendo {config.features_source}")
    splits = split_panel(read_features(spark, config))
    print(
        f"treino={len(splits.train):,} validacao={len(splits.validation):,} "
        f"teste={len(splits.test):,} inferencia={len(splits.inference):,} "
        f"descartadas={splits.n_discarded:,}"
    )

    if splits.inference.empty:
        # Sem corte de inferência não há o que prever, e gravar um quadro vazio apagaria as linhas do modelo.
        raise ValueError("nenhuma linha de inferência (corte sem alvo completo): nada a prever")

    glm_config = dataclasses.replace(
        FEATURE_STEPS[args.step],
        name=args.model_name,
        family=args.family,
        power=args.power,
        alpha=args.alpha,
    )
    treino = (
        splits.train
        if args.fit_on == "treino"
        else pd.concat([splits.train, splits.validation, splits.test], ignore_index=True)
    )
    modelo = fit_glm(treino, glm_config)
    print(
        f"modelo '{args.model_name}' ({args.family}) treinado em {modelo.n_train:,} linhas; "
        f"dispersao de Pearson={modelo.dispersao_pearson:.3f}"
    )

    teste = add_predictions(splits.test, modelo, "pred_glm")
    teste["pred_regua"] = teste[BASELINE_COL]
    if args.fit_on == "treino":
        print("\ndesempenho no teste (12 cortes mais recentes com alvo conhecido):")
        print(comparison_scorecard(teste, {"regua": "pred_regua", args.model_name: "pred_glm"}))

    inferencia = add_predictions(splits.inference, modelo, "pred_glm")
    ultimo_corte = inferencia["cutoff"].max()
    recente = inferencia[inferencia["cutoff"] == ultimo_corte]
    mensal = decompose_months(recente, "pred_glm")
    print(
        f"\nprevisao a partir do corte {ultimo_corte}: {len(recente):,} series x 3 meses "
        f"= {len(mensal):,} linhas ({mensal['mes_previsto'].min()} a {mensal['mes_previsto'].max()})"
    )

    agora = dt.datetime.now()
    power = None if args.family == "poisson" else args.power
    # Com --fit-on completo o modelo já viu as linhas de teste: são linhas de treino, e rotulá-las
    # "teste" contaminaria qualquer avaliação fora da amostra feita depois sobre a tabela.
    split_teste = "teste" if args.fit_on == "treino" else "treino"
    tabela_3m = pd.concat(
        [
            build_forecast_3m_frame(
                teste, "pred_glm", args.model_name, args.family, power, args.alpha, split_teste, agora
            ),
            build_forecast_3m_frame(
                inferencia,
                "pred_glm",
                args.model_name,
                args.family,
                power,
                args.alpha,
                "inferencia",
                agora,
            ),
        ],
        ignore_index=True,
    )
    tabela_mensal = build_forecast_mensal_frame(mensal, "pred_glm", args.model_name, agora)

    if args.dry_run:
        print("--dry-run: nada gravado")
        return

    n3 = write_forecast_3m(spark, tabela_3m, args.model_name, config)
    print(f"gravadas {n3:,} linhas em {config.forecast_target}")
    nm = write_forecast_mensal(spark, tabela_mensal, args.model_name, config)
    print(f"gravadas {nm:,} linhas em {config.forecast_monthly_target}")


if __name__ == "__main__":
    main()
