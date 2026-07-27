import argparse
import subprocess
import sys

STEPS = {
    "deps": ["dbt", "deps"],
    "intermediate_run": ["dbt", "run", "--select", "intermediate"],
    "intermediate_test": ["dbt", "test", "--select", "intermediate"],
    "marts_run": ["dbt", "run", "--select", "marts"],
    "marts_test": ["dbt", "test", "--select", "marts"],
    "apply_masks": ["dbt", "run-operation", "apply_column_masks"],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Wrapper para execucao de steps dbt no Databricks")
    parser.add_argument("--step", required=True, choices=list(STEPS.keys()), help="Step dbt a ser executado")
    parser.add_argument("--target", default="dev", help="Target do dbt (dev/prod)")
    return parser.parse_args()


def main():
    args = parse_args()
    cmd = STEPS[args.step] + ["--target", args.target]
    result = subprocess.run(cmd, capture_output=False, text=True)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
