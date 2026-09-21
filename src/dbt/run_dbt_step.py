import argparse
import os
import sys
import tempfile
import shutil
from pathlib import Path

SECRET_SCOPE = "lh_nautical"
_SECRET_ENV_MAP = {
    "DBT_HTTP_PATH": "dbt_http_path",
    "DBT_DATABRICKS_TOKEN": "dbt_databricks_token",
}

STEPS = {
    "deps": ["deps"],
    # Cria (idempotente) as funcoes de mascara antes de qualquer model rodar.
    "create_mask_functions": ["run-operation", "create_mask_functions"],
    # Carrega os seeds (seeds/) e roda os testes deles. Precisa vir antes de
    # intermediate_run: int_uf_coordinates faz ref ao seed de coordenadas.
    "seed": ["build", "--select", "resource_type:seed"],
    # int_customers/int_employees/int_suppliers e dim_customers/dim_employees/
    # dim_suppliers tem post_hook (macro mask_post_hooks) que reaplica a
    # mascara na sequencia imediata da criacao de cada tabela
    "intermediate_run": ["run", "--select", "intermediate"],
    "intermediate_test": ["test", "--select", "intermediate"],
    "marts_run": ["run", "--select", "marts"],
    # indirect-selection=cautious: o default do dbt (eager) inclui um teste
    # na selecao se QUALQUER parent dele estiver selecionado. Os testes
    # relationships de agg_demand_daily/weekly (pasta ml) tem
    # dim_products/dim_locations (pasta marts) como parent, e vazariam para
    # dentro do --select marts mesmo agg_demand_* ainda nao existindo nesse
    # ponto do pipeline (ml_run so roda depois de marts_test). Cautious so
    # inclui um teste se TODOS os parents estiverem selecionados.
    "marts_test": ["test", "--select", "marts", "--indirect-selection", "cautious"],
    # Reaplica a mascara em todas as tabelas Silver e Gold de uma vez — os
    # post-hooks acima ja cobrem o caso comum; este step e uma segunda
    # camada de garantia.
    "apply_masks": ["run-operation", "apply_column_masks"],
    "ml_run": ["run", "--select", "ml"],
    "ml_test": ["test", "--select", "ml"],
}


def _find_bundle_root() -> str | None:
    candidate = Path.cwd()
    for _ in range(5):
        if (candidate / "profiles.yml").is_file():
            return str(candidate)
        parent = candidate.parent
        if parent == candidate:
            break
        candidate = parent
    return None


def _load_secrets(target: str):
    env_map = dict(_SECRET_ENV_MAP)
    # Em prod o profiles.yml exige DBT_DATABRICKS_TOKEN_PROD; sem ele o dbt
    # falha no parse com uma mensagem que nao aponta o secret ausente.
    required = set()
    if target == "prod":
        env_map["DBT_DATABRICKS_TOKEN_PROD"] = "dbt_databricks_token_prod"
        required.add("DBT_DATABRICKS_TOKEN_PROD")

    try:
        from databricks.sdk.runtime import dbutils
    except ImportError:
        return

    for env_var, secret_key in env_map.items():
        if env_var in os.environ:
            continue
        try:
            value = dbutils.secrets.get(scope=SECRET_SCOPE, key=secret_key)
        except Exception as exc:
            if env_var in required:
                raise RuntimeError(
                    f"Secret '{SECRET_SCOPE}/{secret_key}' nao encontrado ou "
                    f"sem permissao de leitura (necessario para "
                    f"--target {target}): {exc}"
                ) from exc
            continue
        if value:
            os.environ[env_var] = value


def main():
    parser = argparse.ArgumentParser(
        description="Wrapper para execucao de steps dbt no Databricks")
    parser.add_argument("--step", required=True)
    parser.add_argument("--target", default="dev")
    args = parser.parse_args()

    if args.step not in STEPS:
        print(
            f"Step '{args.step}' invalido. Disponiveis: {sorted(STEPS.keys())}", file=sys.stderr)
        sys.exit(1)

    bundle_root = _find_bundle_root()

    if "DBT_PROFILES_DIR" not in os.environ:
        os.environ["DBT_PROFILES_DIR"] = bundle_root or os.getcwd()

    _load_secrets(args.target)

    dbt_args = STEPS[args.step] + ["--target", args.target]
    if bundle_root:
        dbt_args.extend(["--project-dir", bundle_root])

    from dbt.cli.main import dbtRunner
    runner = dbtRunner()
    result = runner.invoke(dbt_args)

    if not result.success:
        if result.exception:
            print(f"dbt exception: {result.exception}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
