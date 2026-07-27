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
    "intermediate_run": ["run", "--select", "intermediate"],
    "intermediate_test": ["test", "--select", "intermediate"],
    "marts_run": ["run", "--select", "marts"],
    "marts_test": ["test", "--select", "marts"],
    "apply_masks": ["run-operation", "apply_column_masks"],
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
    if target == "prod":
        env_map["DBT_DATABRICKS_TOKEN_PROD"] = "dbt_databricks_token"

    try:
        from databricks.sdk.runtime import dbutils
        for env_var, secret_key in env_map.items():
            if env_var not in os.environ:
                try:
                    value = dbutils.secrets.get(scope=SECRET_SCOPE, key=secret_key)
                    if value:
                        os.environ[env_var] = value
                except Exception:
                    pass
    except ImportError:
        pass


def main():
    parser = argparse.ArgumentParser(description="Wrapper para execucao de steps dbt no Databricks")
    parser.add_argument("--step", required=True)
    parser.add_argument("--target", default="dev")
    args = parser.parse_args()

    if args.step not in STEPS:
        print(f"Step '{args.step}' invalido. Disponiveis: {sorted(STEPS.keys())}", file=sys.stderr)
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
