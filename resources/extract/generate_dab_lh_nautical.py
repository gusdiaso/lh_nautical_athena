"""Gera o YAML do DAB (Databricks Asset Bundle) para extração."""

import sys
from pathlib import Path

# Adiciona src/ingestion ao path para importar config
sys.path.insert(0, str(Path(__file__).parents[2] / "src" / "ingestion"))
from config import TABLES

# Template de uma task
TASK_TEMPLATE = """\
        - task_key: extract_{table}
          environment_key: default
          spark_python_task:
            python_file: ../../src/ingestion/extract_lh_nautical.py
            parameters:
              - --table
              - {table}
              - --catalog
              - ${{var.catalog}}
              - --schema
              - ${{var.schema}}
          max_retries: 1"""

# Template completo do YAML
YAML_TEMPLATE = """\
# ╔══════════════════════════════════════════════════════════════╗
# ║  ARQUIVO GERADO AUTOMATICAMENTE - NÃO EDITAR MANUALMENTE     ║
# ║  Execute: python generate_dab.py para regenerar              ║
# ╚══════════════════════════════════════════════════════════════╝

# Variáveis reutilizáveis do job
variables:
  catalog:
    description: 'Catálogo no Unity Catalog'
  schema:
    description: 'Schema de destino no Unity Catalog'
    default: bronze

# Valores por ambiente
targets:
  dev:
    variables:
      catalog: dev_lh_nautical
      schema: bronze

  prod:
    variables:
      catalog: prod_lh_nautical
      schema: bronze
    resources:
      jobs:
        extract_lh_nautical:
          email_notifications:
            on_failure:
              - lh-team-athena-bb-aaaavi2j2f5jb7k23os5chjvuu@indiciumai.slack.com

# Job de extração para a camada Bronze
resources:
  jobs:
    extract_lh_nautical:
      name: extract_lh_nautical
      description: 'Job que executa uma task para cada tabela e grava os dados no formato Delta.'
      max_concurrent_runs: 1

      environments:
        - environment_key: default
          spec:
            environment_version: '2'
            dependencies:
              - tenacity

      # Uma task por tabela (gerado automaticamente)
      tasks:
{tasks}
"""


def generate_yaml() -> None:
    """Gera o YAML do DAB a partir da lista de tabelas em config.py."""
    # Gera as tasks a partir da lista de tabelas
    tasks = "\n".join(TASK_TEMPLATE.format(table=table) for table in TABLES)

    # Monta o YAML completo
    yaml_content = YAML_TEMPLATE.format(tasks=tasks)

    # Caminho de saída
    output_path = Path(__file__).parent / "extract_lh_nautical.yml"
    output_path.write_text(yaml_content, encoding="utf-8")

    print(f"YAML gerado: {output_path}")
    print(f"Total de tasks: {len(TABLES)}")


if __name__ == "__main__":
    generate_yaml()
