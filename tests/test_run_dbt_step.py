import importlib.util
import sys
import types
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "src" / "dbt" / "run_dbt_step.py"

_ENV_VARS = ("DBT_HTTP_PATH", "DBT_DATABRICKS_TOKEN", "DBT_DATABRICKS_TOKEN_PROD")


@pytest.fixture
def run_dbt_step():
    spec = importlib.util.spec_from_file_location("run_dbt_step", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in _ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def _fake_dbutils(monkeypatch, secrets):
    """Instala um databricks.sdk.runtime.dbutils falso com `secrets` {key: valor}."""

    def get(scope, key):
        if key not in secrets:
            raise Exception(f"Secret does not exist with scope: {scope} and key: {key}")
        return secrets[key]

    dbutils = types.SimpleNamespace(secrets=types.SimpleNamespace(get=get))
    runtime = types.ModuleType("databricks.sdk.runtime")
    runtime.dbutils = dbutils
    monkeypatch.setitem(sys.modules, "databricks", types.ModuleType("databricks"))
    monkeypatch.setitem(sys.modules, "databricks.sdk", types.ModuleType("databricks.sdk"))
    monkeypatch.setitem(sys.modules, "databricks.sdk.runtime", runtime)


def test_prod_carrega_token_prod(monkeypatch, run_dbt_step):
    _fake_dbutils(monkeypatch, {
        "dbt_http_path": "sql/1.0/warehouses/x",
        "dbt_databricks_token": "dev-token",
        "dbt_databricks_token_prod": "prod-token",
    })

    run_dbt_step._load_secrets("prod")

    import os
    assert os.environ["DBT_DATABRICKS_TOKEN_PROD"] == "prod-token"


def test_prod_sem_secret_falha_com_mensagem_clara(monkeypatch, run_dbt_step):
    _fake_dbutils(monkeypatch, {
        "dbt_http_path": "sql/1.0/warehouses/x",
        "dbt_databricks_token": "dev-token",
    })

    with pytest.raises(RuntimeError, match="lh_nautical/dbt_databricks_token_prod"):
        run_dbt_step._load_secrets("prod")


def test_dev_nao_exige_token_prod(monkeypatch, run_dbt_step):
    _fake_dbutils(monkeypatch, {
        "dbt_http_path": "sql/1.0/warehouses/x",
        "dbt_databricks_token": "dev-token",
    })

    run_dbt_step._load_secrets("dev")

    import os
    assert os.environ["DBT_DATABRICKS_TOKEN"] == "dev-token"
    assert "DBT_DATABRICKS_TOKEN_PROD" not in os.environ
