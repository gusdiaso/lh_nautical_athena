"""Testes do executável do XGBoost (`run_demand_xgboost`): argumentos e saídas.

O `main` recebe uma sessão falsa cuja tabela é um pandas: `load_panel`, `run` e a
gravação dos CSVs rodam de verdade, sem Spark.
"""

import sys

import pandas as pd
import pytest

from src.analytics_ai import run_demand_xgboost as module
from src.analytics_ai.demand_xgboost import COLUMNS


class _Table:
    def __init__(self, frame):
        self.frame = frame
        self.selected = None

    def select(self, *columns):
        self.selected = columns
        return self

    def toPandas(self):  # noqa: N802 - nome da API do Spark
        return self.frame[list(self.selected)].copy()


class _Spark:
    def __init__(self, frame):
        self.table_name = None
        self._table = _Table(frame)

    def table(self, name):
        self.table_name = name
        return self._table


# ── main: validação de argumentos ───────────────────────────────────


def _run_main(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["run_demand_xgboost", *args])
    module.main()


def test_main_rejects_duplicate_output_names(monkeypatch, capsys):
    monkeypatch.setattr(module, "create_spark_session", lambda: pytest.fail("não deve abrir sessão antes de validar"))
    with pytest.raises(SystemExit) as saida:
        _run_main(monkeypatch, "--test-output", "x.csv", "--forecast-output", "x.csv")
    assert saida.value.code == 2
    assert "quatro nomes distintos" in capsys.readouterr().err


@pytest.mark.parametrize("option", ["--test-output", "--forecast-output", "--metrics-output", "--search-output"])
@pytest.mark.parametrize(
    "protected",
    [
        "previsoes_teste.csv",
        "previsoes_atuais.csv",
        "previsoes_teste_calibradas.csv",
        "previsoes_atuais_calibradas.csv",
        "comparacao_calibracao_validacao.csv",
    ],
)
def test_main_never_overwrites_the_original_csvs(monkeypatch, tmp_path, option, protected):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(module, "create_spark_session", lambda: pytest.fail("não deve abrir sessão antes de validar"))
    with pytest.raises(SystemExit) as saida:
        _run_main(monkeypatch, option, protected)
    assert saida.value.code == 2
    assert not (tmp_path / protected).exists()


def test_main_help_mentions_the_outputs(monkeypatch, capsys):
    with pytest.raises(SystemExit) as saida:
        _run_main(monkeypatch, "--help")
    assert saida.value.code == 0
    ajuda = capsys.readouterr().out
    for opcao in ("--test-output", "--forecast-output", "--metrics-output", "--search-output"):
        assert opcao in ajuda


# ── main: execução completa ─────────────────────────────────────────


def test_main_end_to_end_writes_the_four_csvs(monkeypatch, tmp_path, capsys, demand_panel):
    monkeypatch.chdir(tmp_path)
    spark = _Spark(demand_panel.copy())
    monkeypatch.setattr(module, "create_spark_session", lambda: spark)
    _run_main(monkeypatch)
    saida = capsys.readouterr().out

    assert spark.table_name.endswith(".ml_features_produto_loja_mes")
    assert spark._table.selected == COLUMNS  # só as colunas necessárias saem do Delta
    for trecho in ("Validação:", "Teste:", "Parâmetros escolhidos:", "Conjunto escolhido na validação:", "Corte de inferência: 2024-12-01"):
        assert trecho in saida, trecho

    teste = pd.read_csv(tmp_path / "previsoes_teste_xgboost_offset_duas_etapas.csv")
    assert len(teste) == 12 * 10  # 12 cortes de teste x 10 séries
    assert {"pred_xgboost", "pred_calibrated", "pred_reconciled", "pred_two_stage", "target_3m"} <= set(teste.columns)
    atuais = pd.read_csv(tmp_path / "previsoes_atuais_xgboost_offset_duas_etapas.csv")
    assert len(atuais) == 10 and set(atuais["cutoff"]) == {"2024-12-01"}
    metricas = pd.read_csv(tmp_path / "metricas_xgboost_offset_duas_etapas.csv")
    assert set(metricas["particao"]) == {"validacao", "teste"}
    assert {"modelo", "wape", "vies", "mae", "rmse"} <= set(metricas.columns)
    busca = pd.read_csv(tmp_path / "busca_validacao_xgboost_offset_duas_etapas.csv")
    assert set(busca["experimento"]) == {"base_margin", "duas_etapas", "residual"}


def test_main_custom_output_paths(monkeypatch, tmp_path, demand_panel, xgboost_result):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(module, "create_spark_session", lambda: _Spark(demand_panel.copy()))
    monkeypatch.setattr(module, "run", lambda panel: xgboost_result)  # o run tem teste próprio; aqui só as saídas
    _run_main(monkeypatch, "--test-output", "a.csv", "--forecast-output", "b.csv", "--metrics-output", "c.csv", "--search-output", "d.csv")
    assert sorted(p.name for p in tmp_path.glob("*.csv")) == ["a.csv", "b.csv", "c.csv", "d.csv"]
