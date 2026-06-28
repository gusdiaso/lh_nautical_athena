"""Este arquivo configura o pytest, inicializa o Databricks Connect e fornece fixtures para Spark e carregamento de dados de teste."""

import csv
import json
import os
import sys
import pathlib
from contextlib import contextmanager

try:
    import pytest
    from databricks.connect import DatabricksSession
    from databricks.sdk import WorkspaceClient
    from pyspark.sql import SparkSession
except ImportError:
    raise ImportError(
        "Dependências de teste não encontradas.\n\n"
        "Execute os testes com 'uv run pytest'. Veja http://docs.astral.sh/uv para mais informações sobre uv."
    )


@pytest.fixture()
def spark() -> SparkSession:
    """Fornece uma fixture SparkSession para testes.

    Exemplo mínimo:
        def test_uses_spark(spark):
            df = spark.createDataFrame([(1,)], ["x"])
            assert df.count() == 1

    Returns:
        Instância SparkSession conectada ao Databricks.
    """
    return DatabricksSession.builder.getOrCreate()


@pytest.fixture()
def load_fixture(spark: SparkSession):
    """Fornece uma callable para carregar JSON ou CSV do diretório fixtures/.

    Exemplo de uso:

        def test_using_fixture(load_fixture):
            data = load_fixture("my_data.json")
            assert data.count() >= 1

    Returns:
        Callable que carrega arquivos de fixture em DataFrames.
    """

    def _loader(filename: str):
        path = pathlib.Path(__file__).parent.parent / "fixtures" / filename
        suffix = path.suffix.lower()
        if suffix == ".json":
            rows = json.loads(path.read_text())
            return spark.createDataFrame(rows)
        if suffix == ".csv":
            with path.open(newline="") as f:
                rows = list(csv.DictReader(f))
            return spark.createDataFrame(rows)
        raise ValueError(f"Tipo de fixture não suportado para: {filename}")

    return _loader


def _enable_fallback_compute():
    """Habilita compute serverless se nenhum compute for especificado."""
    conf = WorkspaceClient().config
    if conf.serverless_compute_id or conf.cluster_id or os.environ.get("SPARK_REMOTE"):
        return

    url = "https://docs.databricks.com/dev-tools/databricks-connect/cluster-config"
    print("nenhum compute especificado, usando serverless compute", file=sys.stderr)
    print(f"  veja {url} para configuração manual", file=sys.stdout)

    os.environ["DATABRICKS_SERVERLESS_COMPUTE_ID"] = "auto"


@contextmanager
def _allow_stderr_output(config: pytest.Config):
    """Habilita temporariamente a captura de saída do pytest."""
    capman = config.pluginmanager.get_plugin("capturemanager")
    if capman:
        with capman.global_and_fixture_disabled():
            yield
    else:
        yield


def pytest_configure(config: pytest.Config):
    """Configura a sessão do pytest."""
    with _allow_stderr_output(config):
        _enable_fallback_compute()

        # Inicializa a sessão Spark de forma eager, para que esteja disponível
        # mesmo quando SparkSession.builder.getOrCreate() é usado. Para
        # DB Connect 15+, validamos a compatibilidade de versão com o cluster remoto.
        if hasattr(DatabricksSession.builder, "validateSession"):
            DatabricksSession.builder.validateSession().getOrCreate()
        else:
            DatabricksSession.builder.getOrCreate()
