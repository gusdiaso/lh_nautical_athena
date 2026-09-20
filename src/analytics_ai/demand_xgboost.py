"""Primeiro XGBoost para a demanda total dos três meses após cada corte."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping

import numpy as np
import pandas as pd

from src.analytics_ai.demand_common import HORIZON, add_months, as_bool, cutoff_months
from src.analytics_ai.ml_config import MlFeatureConfig

TARGET = "target_3m"
BASELINE = "baseline_pred_categoria_local_idx_trend"
FEATURES = (
    "categoria_local_avg_12m",
    "season_sum_next_3m",
    "growth_12m",
    "trend_factor",
    BASELINE,
)
HISTORY_FEATURES = (
    "sum_3m", "sum_12m", "avg_monthly_3m", "avg_monthly_12m",
    "months_with_sale_12m", "months_since_last_sale", "is_stopped_12m",
)
CROSS_STORE_FEATURES = (
    "produto_locais_avg_12m", "produto_locais_n_locations", "categoria_local_n_series",
)
FEATURE_SETS = {
    "modelo_atual": FEATURES,
    "modelo_atual_historico_serie": FEATURES + HISTORY_FEATURES,
    "modelo_atual_historico_outras_lojas": FEATURES + HISTORY_FEATURES + CROSS_STORE_FEATURES,
}
COLUMNS = tuple(dict.fromkeys((
    "cutoff", "sk_product", "sk_location", "category_name",
    "is_target_complete", "trend_ready", TARGET, "sum_3m", "sum_12m",
    "produto_locais_avg_12m", *dict.fromkeys(sum(FEATURE_SETS.values(), ())),
)))


@dataclass(frozen=True)
class TemporalSplit:
    train: pd.DataFrame
    validation: pd.DataFrame
    final_train: pd.DataFrame
    test: pd.DataFrame
    validation_cutoffs: tuple
    test_cutoffs: tuple


@dataclass(frozen=True)
class Calibration:
    name: str
    xgb_weight: float
    multiplier: float = 1.0


@dataclass(frozen=True)
class XgbParameters:
    max_depth: int
    min_child_weight: int
    learning_rate: float
    n_estimators: int
    subsample: float
    reg_lambda: float


WINNING_PARAMETERS = XgbParameters(3, 10, 0.10, 150, 0.9, 5.0)


# Busca dirigida de 12 configurações; inclui a primeira versão e varia os seis
# parâmetros solicitados sem fazer o produto cartesiano completo.
PARAMETER_CANDIDATES = (
    XgbParameters(3, 10, 0.05, 250, 0.9, 5.0),
    XgbParameters(2, 10, 0.05, 250, 0.9, 5.0),
    XgbParameters(4, 10, 0.05, 250, 0.9, 5.0),
    XgbParameters(3, 5, 0.05, 250, 0.9, 5.0),
    XgbParameters(3, 20, 0.05, 250, 0.9, 5.0),
    XgbParameters(3, 10, 0.03, 400, 0.9, 5.0),
    XgbParameters(3, 10, 0.10, 150, 0.9, 5.0),
    XgbParameters(3, 10, 0.05, 250, 0.8, 5.0),
    XgbParameters(3, 10, 0.05, 250, 1.0, 5.0),
    XgbParameters(3, 10, 0.05, 250, 0.9, 1.0),
    XgbParameters(3, 10, 0.05, 250, 0.9, 10.0),
    XgbParameters(2, 20, 0.03, 400, 0.8, 10.0),
)


def feature_table_name(config: MlFeatureConfig) -> str:
    return f"{config.catalog}.{config.schema}.ml_features_produto_loja_mes"


def load_panel(spark, config: MlFeatureConfig | None = None) -> pd.DataFrame:
    """Lê apenas as colunas necessárias da tabela dbt já materializada."""
    config = config or MlFeatureConfig.from_environment_monthly()
    panel = spark.table(feature_table_name(config)).select(*COLUMNS).toPandas()
    all_features = tuple(dict.fromkeys(sum(FEATURE_SETS.values(), ())))
    all_features = tuple(dict.fromkeys((*all_features, "sum_3m", "sum_12m", "produto_locais_avg_12m")))
    for column in (TARGET, *all_features):
        panel[column] = pd.to_numeric(panel[column]).astype(float)
    return panel


def temporal_split(panel: pd.DataFrame, validation_months: int = 6, test_months: int = 12) -> TemporalSplit:
    """Separa cortes sem permitir rótulos ainda desconhecidos na origem seguinte.

    Para avaliar um corte T, o treino termina em T-3, pois só então os três
    meses de seu alvo já aconteceram. O mesmo embargo vale na validação e no
    ajuste final anterior ao teste. Os 12 últimos cortes rotulados ficam no
    teste, como na régua do notebook 04.
    """
    if validation_months < 1 or test_months < 1:
        raise ValueError("validation_months e test_months devem ser positivos")
    data = panel.copy()
    data["cutoff"] = pd.to_datetime(data["cutoff"]).dt.date
    labeled = data.loc[as_bool(data["is_target_complete"])].copy()
    eligible = labeled.loc[as_bool(labeled["trend_ready"])].copy()
    last_cutoff = eligible["cutoff"].max()
    if pd.isna(last_cutoff):
        raise ValueError("Não há cortes rotulados com tendência disponível")
    test_cutoffs = tuple(cutoff_months(add_months(last_cutoff, HORIZON), test_months))
    validation_cutoffs = tuple(
        add_months(test_cutoffs[0], -validation_months + offset)
        for offset in range(validation_months)
    )
    available = set(eligible["cutoff"])
    if not set((*validation_cutoffs, *test_cutoffs)) <= available:
        raise ValueError("Faltam cortes completos para validação ou teste")

    train_end = add_months(validation_cutoffs[0], -HORIZON)
    final_train_end = add_months(test_cutoffs[0], -HORIZON)
    train = eligible.loc[eligible["cutoff"] <= train_end].copy()
    final_train = eligible.loc[eligible["cutoff"] <= final_train_end].copy()
    validation = eligible.loc[eligible["cutoff"].isin(validation_cutoffs)].copy()
    test = eligible.loc[eligible["cutoff"].isin(test_cutoffs)].copy()
    if train.empty or validation.empty or final_train.empty or test.empty:
        raise ValueError("Histórico insuficiente para a separação temporal")
    return TemporalSplit(train, validation, final_train, test, validation_cutoffs, test_cutoffs)


def _matrix(frame: pd.DataFrame, features: tuple[str, ...] = FEATURES) -> pd.DataFrame:
    return frame.loc[:, features].astype(float)


def _fit(frame: pd.DataFrame, parameters: XgbParameters, features: tuple[str, ...] = FEATURES):
    import xgboost as xgb

    matrix = xgb.DMatrix(_matrix(frame, features), label=frame[TARGET].to_numpy(dtype=float))
    return xgb.train(
        {
            "objective": "count:poisson",
            "max_depth": parameters.max_depth,
            "eta": parameters.learning_rate,
            "subsample": parameters.subsample,
            "colsample_bytree": 1.0,
            "min_child_weight": parameters.min_child_weight,
            "lambda": parameters.reg_lambda,
            "seed": 42,
            "nthread": 4,
            "tree_method": "hist",
        },
        matrix,
        num_boost_round=parameters.n_estimators,
    )


BASE_MARGIN_EPSILONS = (1e-6, 1e-3, 1e-2)
EXPERIMENT_PARAMETERS = (WINNING_PARAMETERS, PARAMETER_CANDIDATES[0], PARAMETER_CANDIDATES[1])


def _margin(frame: pd.DataFrame, epsilon: float) -> np.ndarray:
    return np.log(np.maximum(frame[BASELINE].to_numpy(dtype=float), 0.0) + epsilon)


def _fit_base_margin(frame: pd.DataFrame, parameters: XgbParameters, epsilon: float, features: tuple[str, ...] = FEATURES):
    import xgboost as xgb

    matrix = xgb.DMatrix(_matrix(frame, features), label=frame[TARGET].to_numpy(dtype=float))
    matrix.set_base_margin(_margin(frame, epsilon))
    return xgb.train(
        {"objective": "count:poisson", "max_depth": parameters.max_depth, "eta": parameters.learning_rate,
         "subsample": parameters.subsample, "colsample_bytree": 1.0,
         "min_child_weight": parameters.min_child_weight, "lambda": parameters.reg_lambda,
         "seed": 42, "nthread": 4, "tree_method": "hist"}, matrix,
        num_boost_round=parameters.n_estimators,
    )


def predict_base_margin(model, frame: pd.DataFrame, epsilon: float, features: tuple[str, ...] = FEATURES) -> np.ndarray:
    import xgboost as xgb

    matrix = xgb.DMatrix(_matrix(frame, features))
    matrix.set_base_margin(_margin(frame, epsilon))
    return np.maximum(model.predict(matrix), 0.0)


def _fit_two_stage(frame: pd.DataFrame, parameters: XgbParameters, features: tuple[str, ...] = FEATURES):
    import xgboost as xgb

    positive = frame[TARGET].to_numpy(dtype=float) > 0
    classifier = xgb.train(
        {"objective": "binary:logistic", "max_depth": parameters.max_depth, "eta": parameters.learning_rate,
         "subsample": parameters.subsample, "colsample_bytree": 1.0,
         "min_child_weight": parameters.min_child_weight, "lambda": parameters.reg_lambda,
         "seed": 42, "nthread": 4, "tree_method": "hist"},
        xgb.DMatrix(_matrix(frame, features), label=positive.astype(float)),
        num_boost_round=parameters.n_estimators,
    )
    positive_frame = frame.loc[positive]
    regressor = xgb.train(
        {"objective": "count:poisson", "max_depth": parameters.max_depth, "eta": parameters.learning_rate,
         "subsample": parameters.subsample, "colsample_bytree": 1.0,
         "min_child_weight": parameters.min_child_weight, "lambda": parameters.reg_lambda,
         "seed": 42, "nthread": 4, "tree_method": "hist"},
        xgb.DMatrix(_matrix(positive_frame, features), label=positive_frame[TARGET].to_numpy(dtype=float)),
        num_boost_round=parameters.n_estimators,
    )
    return classifier, regressor


def predict_two_stage(models, frame: pd.DataFrame, features: tuple[str, ...] = FEATURES) -> tuple[np.ndarray, np.ndarray]:
    import xgboost as xgb

    classifier, regressor = models
    matrix = xgb.DMatrix(_matrix(frame, features))
    probability = np.clip(classifier.predict(matrix), 0.0, 1.0)
    quantity = np.maximum(regressor.predict(matrix), 0.0)
    return probability * quantity, probability


def _fit_residual(frame: pd.DataFrame, parameters: XgbParameters, features: tuple[str, ...] = FEATURES):
    import xgboost as xgb

    target = np.log1p(np.maximum(frame[TARGET].to_numpy(dtype=float), 0.0)) - np.log1p(
        np.maximum(frame[BASELINE].to_numpy(dtype=float), 0.0)
    )
    return xgb.train(
        {
            "objective": "reg:squarederror",
            "max_depth": parameters.max_depth,
            "eta": parameters.learning_rate,
            "subsample": parameters.subsample,
            "colsample_bytree": 1.0,
            "min_child_weight": parameters.min_child_weight,
            "lambda": parameters.reg_lambda,
            "seed": 42,
            "nthread": 4,
            "tree_method": "hist",
        },
        xgb.DMatrix(_matrix(frame, features), label=target),
        num_boost_round=parameters.n_estimators,
    )


def predict_nonnegative(model, frame: pd.DataFrame, features: tuple[str, ...] = FEATURES) -> np.ndarray:
    import xgboost as xgb

    return np.maximum(model.predict(xgb.DMatrix(_matrix(frame, features))), 0.0)


def predict_residual(model, frame: pd.DataFrame, features: tuple[str, ...] = FEATURES) -> np.ndarray:
    import xgboost as xgb

    return model.predict(xgb.DMatrix(_matrix(frame, features)))


def reconstruct_residual(frame: pd.DataFrame, residual: np.ndarray, shift: float = 0.0) -> np.ndarray:
    baseline = np.maximum(frame[BASELINE].to_numpy(dtype=float), 0.0)
    return np.maximum(np.expm1(np.log1p(baseline) + residual + shift), 0.0)


def metric_table(frame: pd.DataFrame, forecasts: Mapping[str, str] | None = None) -> pd.DataFrame:
    """Mesmas linhas para modelo e régua; WAPE/viés como demand_common."""
    from src.analytics_ai.demand_common import aggregated_error_table, error_table

    frame = frame.copy()
    forecasts = forecasts or {"XGBoost puro": "pred_xgboost", "Régua": BASELINE}
    for column in (TARGET, *forecasts.values()):
        frame[column] = pd.to_numeric(frame[column]).astype(float)
    actual = frame[TARGET].to_numpy(dtype=float)
    overall = error_table(frame, forecasts, reference=None).set_index("regua")
    product_location = aggregated_error_table(frame, forecasts, ("sk_product", "sk_location")).set_index("regua")
    category = aggregated_error_table(frame, forecasts, ("category_name", "sk_location")).set_index("regua")
    location = aggregated_error_table(frame, forecasts, ("sk_location",)).set_index("regua")
    rows = []
    for label, col in forecasts.items():
        pred = frame[col].to_numpy(dtype=float)
        error = pred - actual
        rows.append({
            "modelo": label,
            "mae": float(np.mean(np.abs(error))),
            "rmse": float(np.sqrt(np.mean(error ** 2))),
            "wape": float(overall.loc[label, "wape"]),
            "vies": float(overall.loc[label, "vies"]),
            "wape_produto_local": float(product_location.loc[label, "wape"]),
            "wape_categoria_local": float(category.loc[label, "wape"]),
            "wape_local": float(location.loc[label, "wape"]),
        })
    return pd.DataFrame(rows).set_index("modelo")


def evaluate(model, frame: pd.DataFrame, features: tuple[str, ...] = FEATURES) -> tuple[pd.DataFrame, pd.DataFrame]:
    predictions = frame.loc[:, ["cutoff", "sk_product", "sk_location", "category_name", TARGET, BASELINE,
                                "sum_3m", "sum_12m", "season_sum_next_3m", "produto_locais_avg_12m",
                                "categoria_local_avg_12m"]].copy()
    predictions["pred_xgboost"] = predict_nonnegative(model, frame, features)
    return metric_table(predictions), predictions


def apply_calibration(frame: pd.DataFrame, calibration: Calibration) -> np.ndarray:
    xgb = frame["pred_xgboost"].to_numpy(dtype=float)
    baseline = frame[BASELINE].to_numpy(dtype=float)
    calibrated = calibration.xgb_weight * calibration.multiplier * xgb + (1 - calibration.xgb_weight) * baseline
    return np.maximum(calibrated, 0.0)


def reconcile_to_baseline_total(frame: pd.DataFrame, prediction_column: str = "pred_xgboost") -> np.ndarray:
    """Distribui o total da régua usando as proporções do XGBoost."""
    working = frame.reset_index(drop=True)
    predictions = np.maximum(working[prediction_column].to_numpy(dtype=float), 0.0)
    baseline = np.maximum(working[BASELINE].to_numpy(dtype=float), 0.0)
    reconciled = np.zeros(len(working), dtype=float)
    # dropna=False: uma série sem categoria (nula) continua num grupo, em vez de sumir e ficar em zero.
    for _, group in working.groupby(["cutoff", "category_name", "sk_location"], sort=False, dropna=False):
        positions = group.index.to_numpy()
        xgb_total = predictions[positions].sum()
        baseline_total = baseline[positions].sum()
        if xgb_total > 0:
            reconciled[positions] = predictions[positions] * (baseline_total / xgb_total)
        elif baseline_total > 0:
            reconciled[positions] = baseline[positions]
    return np.maximum(reconciled, 0.0)


MOVING_BASELINES = {
    "MM3": "pred_mm3",
    "MM12": "pred_mm12",
    "MM12 × índice": "pred_mm12_idx",
    "Produto nos locais × índice": "pred_produto_idx",
    "Categoria × loja × índice": "pred_categoria_loja_idx",
}


def add_moving_average_baselines(frame: pd.DataFrame) -> pd.DataFrame:
    """Reconstrói as réguas do notebook 04 com colunas existentes no painel."""
    result = frame.copy()
    result["pred_mm3"] = result["sum_3m"].astype(float)
    result["pred_mm12"] = result["sum_12m"].astype(float) / 12.0 * HORIZON
    result["pred_mm12_idx"] = result["sum_12m"].astype(float) / 12.0 * result["season_sum_next_3m"].astype(float)
    result["pred_produto_idx"] = result["produto_locais_avg_12m"].astype(float) / 12.0 * result["season_sum_next_3m"].astype(float)
    result["pred_categoria_loja_idx"] = result["categoria_local_avg_12m"].astype(float) / 12.0 * result["season_sum_next_3m"].astype(float)
    return result


def _calibration_metrics(frame: pd.DataFrame, prediction: np.ndarray) -> dict[str, float]:
    """Pontuação exata na validação, antes de arredondar o relatório."""
    scored = frame.loc[:, ["cutoff", "category_name", "sk_location", TARGET]].copy()
    scored["prediction"] = prediction
    actual_total = scored[TARGET].sum()
    if actual_total <= 0:
        raise ValueError("A validação não possui demanda positiva para calcular WAPE")
    category = scored.groupby(["cutoff", "category_name", "sk_location"], as_index=False)[[TARGET, "prediction"]].sum()
    location = scored.groupby(["cutoff", "sk_location"], as_index=False)[[TARGET, "prediction"]].sum()
    wape_category = (category["prediction"] - category[TARGET]).abs().sum() / actual_total
    wape_location = (location["prediction"] - location[TARGET]).abs().sum() / actual_total
    bias = (scored["prediction"].sum() - actual_total) / actual_total
    return {
        "wape_categoria_local": float(wape_category),
        "wape_local": float(wape_location),
        "vies": float(bias),
        "pontuacao": float(wape_category + wape_location + abs(bias)),
    }


def select_calibration(validation_predictions: pd.DataFrame) -> tuple[Calibration, pd.DataFrame]:
    """Escolhe somente pela validação; menor soma dos três erros vence."""
    actual_total = validation_predictions[TARGET].sum()
    xgb_total = validation_predictions["pred_xgboost"].sum()
    if xgb_total <= 0:
        raise ValueError("A soma das previsões XGBoost na validação deve ser positiva")
    factor = float(actual_total / xgb_total)
    candidates = [
        Calibration("XGBoost puro", 1.0),
        Calibration("XGBoost × fator global", 1.0, factor),
        *(Calibration(f"Mistura {weight}% XGBoost", weight / 100) for weight in range(0, 101, 5)),
    ]
    rows = []
    for candidate in candidates:
        rows.append({
            "alternativa": candidate.name,
            "peso_xgboost": candidate.xgb_weight,
            "fator": candidate.multiplier,
            **_calibration_metrics(validation_predictions, apply_calibration(validation_predictions, candidate)),
        })
    comparison = pd.DataFrame(rows).sort_values("pontuacao", kind="stable").reset_index(drop=True)
    chosen_row = comparison.iloc[0]
    chosen = Calibration(chosen_row["alternativa"], float(chosen_row["peso_xgboost"]), float(chosen_row["fator"]))
    return chosen, comparison


def search_hyperparameters(split: TemporalSplit) -> tuple[XgbParameters, Calibration, pd.DataFrame, pd.DataFrame]:
    """Treina e seleciona apenas por métricas dos seis cortes de validação."""
    rows = []
    best_predictions = None
    best_score = float("inf")
    for number, parameters in enumerate(PARAMETER_CANDIDATES, start=1):
        model = _fit(split.train, parameters)
        _, predictions = evaluate(model, split.validation)
        calibration, candidates = select_calibration(predictions)
        winning_calibration = candidates.iloc[0]
        score = float(winning_calibration["pontuacao"])
        error = apply_calibration(predictions, calibration) - predictions[TARGET].to_numpy(dtype=float)
        actual_total = float(predictions[TARGET].sum())
        rows.append({
            "configuracao": number,
            "max_depth": parameters.max_depth,
            "min_child_weight": parameters.min_child_weight,
            "learning_rate": parameters.learning_rate,
            "n_estimators": parameters.n_estimators,
            "subsample": parameters.subsample,
            "reg_lambda": parameters.reg_lambda,
            "calibracao": calibration.name,
            "peso_xgboost": calibration.xgb_weight,
            "fator": calibration.multiplier,
            "mae": float(np.mean(np.abs(error))),
            "rmse": float(np.sqrt(np.mean(error ** 2))),
            "wape": float(np.abs(error).sum() / actual_total),
            "wape_categoria_local": float(winning_calibration["wape_categoria_local"]),
            "wape_local": float(winning_calibration["wape_local"]),
            "vies": float(winning_calibration["vies"]),
            "pontuacao": score,
        })
        if score < best_score:
            best_score = score
            best_predictions = predictions
    ranking = pd.DataFrame(rows).sort_values("pontuacao", kind="stable").reset_index(drop=True)
    best_row = ranking.iloc[0]
    best_parameters = PARAMETER_CANDIDATES[int(best_row["configuracao"]) - 1]
    best_calibration = Calibration(str(best_row["calibracao"]), float(best_row["peso_xgboost"]), float(best_row["fator"]))
    return best_parameters, best_calibration, ranking, best_predictions


def _score_metrics(metrics: pd.DataFrame, model: str) -> float:
    row = metrics.loc[model]
    return float(row["wape_produto_local"] + row["wape_categoria_local"] + row["wape_local"] + abs(row["vies"]))


def select_residual_shift(validation_frame: pd.DataFrame, residual: np.ndarray) -> tuple[float, pd.DataFrame]:
    """Escolhe deslocamento logarítmico somente nos cortes de validação."""
    actual_log = np.log1p(np.maximum(validation_frame[TARGET].to_numpy(dtype=float), 0.0))
    baseline_log = np.log1p(np.maximum(validation_frame[BASELINE].to_numpy(dtype=float), 0.0))
    mean_shift = float(np.mean(actual_log - baseline_log - residual))
    rows = []
    for shift in (0.0, mean_shift):
        scored = validation_frame.copy()
        scored["pred_residual"] = reconstruct_residual(scored, residual, shift)
        metrics = metric_table(scored, {"XGBoost residual": "pred_residual"})
        rows.append({"shift_log": shift, "pontuacao": _score_metrics(metrics, "XGBoost residual"),
                     "mae": metrics.loc["XGBoost residual", "mae"],
                     "rmse": metrics.loc["XGBoost residual", "rmse"],
                     "wape": metrics.loc["XGBoost residual", "wape"],
                     "vies": metrics.loc["XGBoost residual", "vies"],
                     "wape_produto_local": metrics.loc["XGBoost residual", "wape_produto_local"],
                     "wape_categoria_local": metrics.loc["XGBoost residual", "wape_categoria_local"],
                     "wape_local": metrics.loc["XGBoost residual", "wape_local"]})
    comparison = pd.DataFrame(rows).sort_values("pontuacao", kind="stable").reset_index(drop=True)
    return float(comparison.iloc[0]["shift_log"]), comparison


def select_two_stage_threshold(validation_frame: pd.DataFrame, probabilities: np.ndarray) -> tuple[float, pd.DataFrame]:
    actual = validation_frame[TARGET].to_numpy(dtype=float) > 0
    rows = []
    for threshold in np.arange(0.2, 0.81, 0.05):
        predicted = probabilities >= threshold
        tp = float(np.sum(predicted & actual))
        fp = float(np.sum(predicted & ~actual))
        fn = float(np.sum(~predicted & actual))
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        rows.append({"threshold": threshold, "proportion_real": float(actual.mean()),
                     "proportion_predicted": float(predicted.mean()), "precision": precision,
                     "recall": recall, "f1": f1})
    comparison = pd.DataFrame(rows).sort_values(["f1", "threshold"], ascending=[False, True], kind="stable").reset_index(drop=True)
    return float(comparison.iloc[0]["threshold"]), comparison


def run_feature_experiments(split: TemporalSplit) -> tuple[str, dict, pd.DataFrame]:
    """Treina os três conjuntos e escolhe somente pela validação."""
    experiments = {}
    rows = []
    for name, features in FEATURE_SETS.items():
        model = _fit(split.train, WINNING_PARAMETERS, features)
        _, predictions = evaluate(model, split.validation, features)
        calibration, _ = select_calibration(predictions)
        predictions["pred_calibrated"] = apply_calibration(predictions, calibration)
        predictions["pred_reconciled"] = reconcile_to_baseline_total(predictions)
        forecasts = {
            "XGBoost puro": "pred_xgboost", "Régua": BASELINE,
            "XGBoost calibrado": "pred_calibrated", "XGBoost reconciliado": "pred_reconciled",
        }
        metrics = metric_table(predictions, forecasts)
        scores = {label: _score_metrics(metrics, label) for label in metrics.index}
        selected_model = min(("XGBoost puro", "XGBoost calibrado", "XGBoost reconciliado"), key=scores.get)
        experiments[name] = {
            "features": features, "model": model, "calibration": calibration,
            "validation_predictions": predictions, "validation_metrics": metrics,
            "selected_model": selected_model, "selected_score": scores[selected_model],
        }
        rows.append({
            "conjunto": name, "n_features": len(features), "features": ",".join(features),
            "modelo_selecionado_validacao": selected_model, "pontuacao": scores[selected_model],
            "wape_categoria_local": metrics.loc[selected_model, "wape_categoria_local"],
            "wape_local": metrics.loc[selected_model, "wape_local"],
            "vies": metrics.loc[selected_model, "vies"],
        })
    ranking = pd.DataFrame(rows).sort_values("pontuacao", kind="stable").reset_index(drop=True)
    return str(ranking.iloc[0]["conjunto"]), experiments, ranking


def run(panel: pd.DataFrame) -> dict:
    """Compara os conjuntos de features na validação e congela o vencedor."""
    split = temporal_split(panel)
    selected_set, experiments, feature_search = run_feature_experiments(split)
    chosen = experiments[selected_set]
    features = chosen["features"]
    calibration = chosen["calibration"]
    validation_predictions = add_moving_average_baselines(chosen["validation_predictions"])
    residual_validation_model = _fit_residual(split.train, WINNING_PARAMETERS, FEATURES)
    residual_validation = predict_residual(residual_validation_model, split.validation, FEATURES)
    residual_shift, residual_search = select_residual_shift(validation_predictions, residual_validation)
    validation_predictions["pred_residual"] = reconstruct_residual(validation_predictions, residual_validation, residual_shift)
    base_margin_rows = []
    best_base_margin = None
    for parameters in EXPERIMENT_PARAMETERS:
        for epsilon in BASE_MARGIN_EPSILONS:
            model = _fit_base_margin(split.train, parameters, epsilon, FEATURES)
            candidate = validation_predictions.copy()
            candidate["pred_base_margin"] = predict_base_margin(model, split.validation, epsilon, FEATURES)
            metrics = metric_table(candidate, {"XGBoost base_margin": "pred_base_margin"})
            score = _score_metrics(metrics, "XGBoost base_margin")
            base_margin_rows.append({"max_depth": parameters.max_depth, "min_child_weight": parameters.min_child_weight,
                                     "learning_rate": parameters.learning_rate, "n_estimators": parameters.n_estimators,
                                     "subsample": parameters.subsample, "reg_lambda": parameters.reg_lambda,
                                     "epsilon": epsilon, "pontuacao": score})
            if best_base_margin is None or score < best_base_margin["score"]:
                best_base_margin = {"model": model, "parameters": parameters, "epsilon": epsilon, "score": score,
                                    "prediction": candidate["pred_base_margin"].to_numpy()}
    base_margin_search = pd.DataFrame(base_margin_rows).sort_values("pontuacao", kind="stable").reset_index(drop=True)
    validation_predictions["pred_base_margin"] = best_base_margin["prediction"]

    two_stage_rows = []
    best_two_stage = None
    for parameters in EXPERIMENT_PARAMETERS:
        models = _fit_two_stage(split.train, parameters, FEATURES)
        prediction, probability = predict_two_stage(models, split.validation, FEATURES)
        threshold, classification = select_two_stage_threshold(validation_predictions, probability)
        actual_total = validation_predictions[TARGET].sum()
        factor_candidates = (1.0, float(actual_total / prediction.sum()) if prediction.sum() > 0 else 1.0)
        for factor in factor_candidates:
            candidate = validation_predictions.copy()
            candidate["pred_two_stage"] = np.maximum(prediction * factor, 0.0)
            metrics = metric_table(candidate, {"XGBoost duas etapas": "pred_two_stage"})
            score = _score_metrics(metrics, "XGBoost duas etapas")
            two_stage_rows.append({"max_depth": parameters.max_depth, "min_child_weight": parameters.min_child_weight,
                                   "learning_rate": parameters.learning_rate, "n_estimators": parameters.n_estimators,
                                   "subsample": parameters.subsample, "reg_lambda": parameters.reg_lambda,
                                   "threshold": threshold, "fator": factor, "f1": classification.iloc[0]["f1"],
                                   "pontuacao": score})
            if best_two_stage is None or score < best_two_stage["score"]:
                best_two_stage = {"models": models, "parameters": parameters, "threshold": threshold,
                                  "factor": factor, "score": score, "prediction": prediction * factor,
                                  "probability": probability, "classification": classification}
    two_stage_search = pd.DataFrame(two_stage_rows).sort_values("pontuacao", kind="stable").reset_index(drop=True)
    validation_predictions["pred_two_stage"] = np.maximum(best_two_stage["prediction"], 0.0)
    forecasts = {
        "XGBoost puro": "pred_xgboost", "Régua": BASELINE,
        "XGBoost calibrado": "pred_calibrated", "XGBoost reconciliado": "pred_reconciled",
        "XGBoost residual": "pred_residual",
        "XGBoost base_margin": "pred_base_margin", "XGBoost duas etapas": "pred_two_stage",
    }
    forecasts.update(MOVING_BASELINES)
    validation_metrics = metric_table(validation_predictions, forecasts)
    baseline_rows = []
    for label in MOVING_BASELINES:
        baseline_rows.append({"baseline": label, "pontuacao": _score_metrics(validation_metrics, label),
                              "wape_categoria_local": validation_metrics.loc[label, "wape_categoria_local"],
                              "wape_local": validation_metrics.loc[label, "wape_local"],
                              "vies": validation_metrics.loc[label, "vies"]})
    baseline_ranking = pd.DataFrame(baseline_rows).sort_values("pontuacao", kind="stable").reset_index(drop=True)

    test_model = _fit(split.final_train, WINNING_PARAMETERS, features)
    test_predictions = split.test.loc[:, ["cutoff", "sk_product", "sk_location", "category_name", TARGET, BASELINE,
                                          "sum_3m", "sum_12m", "season_sum_next_3m", "produto_locais_avg_12m",
                                          "categoria_local_avg_12m"]].copy()
    test_predictions["pred_xgboost"] = predict_nonnegative(test_model, split.test, features)
    test_predictions["pred_calibrated"] = apply_calibration(test_predictions, calibration)
    test_predictions["pred_reconciled"] = reconcile_to_baseline_total(test_predictions)
    residual_test_model = _fit_residual(split.final_train, WINNING_PARAMETERS, FEATURES)
    residual_test = predict_residual(residual_test_model, split.test, FEATURES)
    test_predictions["pred_residual"] = reconstruct_residual(test_predictions, residual_test, residual_shift)
    base_margin_test_model = _fit_base_margin(split.final_train, best_base_margin["parameters"], best_base_margin["epsilon"], FEATURES)
    test_predictions["pred_base_margin"] = predict_base_margin(base_margin_test_model, split.test, best_base_margin["epsilon"], FEATURES)
    two_stage_test_models = _fit_two_stage(split.final_train, best_two_stage["parameters"], FEATURES)
    two_stage_test_prediction, two_stage_test_probability = predict_two_stage(two_stage_test_models, split.test, FEATURES)
    test_predictions["pred_two_stage"] = np.maximum(two_stage_test_prediction * best_two_stage["factor"], 0.0)
    test_predictions = add_moving_average_baselines(test_predictions)
    test_metrics = metric_table(test_predictions, forecasts)
    test_metrics_by_cutoff = pd.concat(
        [metric_table(part, forecasts).assign(cutoff=cutoff) for cutoff, part in test_predictions.groupby("cutoff", sort=True)]
    ).reset_index().set_index(["cutoff", "modelo"])

    inference = panel.loc[~as_bool(panel["is_target_complete"]) & as_bool(panel["trend_ready"])].copy()
    inference["cutoff"] = pd.to_datetime(inference["cutoff"]).dt.date
    latest = inference["cutoff"].max()
    if pd.isna(latest):
        raise ValueError("Não há corte de inferência disponível")
    inference = inference.loc[inference["cutoff"] == latest].copy()
    forecast_train_end = add_months(latest, -HORIZON)
    forecast_train = panel.copy()
    forecast_train["cutoff"] = pd.to_datetime(forecast_train["cutoff"]).dt.date
    forecast_train = forecast_train.loc[
        as_bool(forecast_train["is_target_complete"]) & as_bool(forecast_train["trend_ready"])
        & (forecast_train["cutoff"] <= forecast_train_end)
    ]
    if forecast_train.empty:
        raise ValueError("Não há exemplos rotulados para o corte de inferência")
    forecast_model = _fit(forecast_train, WINNING_PARAMETERS, features)
    future_predictions = inference.loc[:, ["cutoff", "sk_product", "sk_location", "category_name", BASELINE,
                                           "sum_3m", "sum_12m", "season_sum_next_3m", "produto_locais_avg_12m",
                                           "categoria_local_avg_12m"]].copy()
    future_predictions["pred_xgboost"] = predict_nonnegative(forecast_model, inference, features)
    future_predictions["pred_calibrated"] = apply_calibration(future_predictions, calibration)
    future_predictions["pred_reconciled"] = reconcile_to_baseline_total(future_predictions)
    residual_forecast_model = _fit_residual(forecast_train, WINNING_PARAMETERS, FEATURES)
    residual_future = predict_residual(residual_forecast_model, inference, FEATURES)
    future_predictions["pred_residual"] = reconstruct_residual(future_predictions, residual_future, residual_shift)
    base_margin_forecast_model = _fit_base_margin(forecast_train, best_base_margin["parameters"], best_base_margin["epsilon"], FEATURES)
    future_predictions["pred_base_margin"] = predict_base_margin(base_margin_forecast_model, inference, best_base_margin["epsilon"], FEATURES)
    two_stage_forecast_models = _fit_two_stage(forecast_train, best_two_stage["parameters"], FEATURES)
    two_stage_future_prediction, _ = predict_two_stage(two_stage_forecast_models, inference, FEATURES)
    future_predictions["pred_two_stage"] = np.maximum(two_stage_future_prediction * best_two_stage["factor"], 0.0)
    future_predictions = add_moving_average_baselines(future_predictions)

    return {
        "split": split, "best_parameters": WINNING_PARAMETERS, "selected_feature_set": selected_set,
        "features": features, "calibration": calibration, "feature_search": feature_search,
        "validation_metrics": validation_metrics, "baseline_ranking": baseline_ranking,
        "residual_shift": residual_shift, "residual_search": residual_search,
        "base_margin_search": base_margin_search, "two_stage_search": two_stage_search,
        "two_stage_classification": best_two_stage["classification"],
        "test_metrics": test_metrics,
        "test_metrics_by_cutoff": test_metrics_by_cutoff, "test_predictions": test_predictions,
        "future_predictions": future_predictions, "test_model": test_model, "forecast_model": forecast_model,
    }
