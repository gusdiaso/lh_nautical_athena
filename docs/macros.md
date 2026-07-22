# Documentação das Macros dbt

## Visão Geral

As macros do dbt neste projeto ficam em `src/dbt/macros/` e concentram a lógica reutilizável do pipeline de transformação.

## Macros Existentes

### `generate_schema_name`

Arquivo: `src/dbt/macros/generate_schema_name.sql`

Evita que o dbt concatene o schema do profile com o schema customizado. O projeto usa diretamente o valor definido em `+schema` no `dbt_project.yml`.

### `sk_from_keys`

Arquivo: `src/dbt/macros/sk_from_keys.sql`

Gera surrogate keys com `md5(concat_ws('||', ...))` a partir de uma ou mais colunas.

### `clean_cep`

Arquivo: `src/dbt/macros/clean_cep.sql`

Remove caracteres não numéricos de CEPs e normaliza o valor para uso analítico.

## Dependências

- `packages.yml` declara `dbt-labs/dbt_utils`.
- `dbt_project.yml` define os schemas e materializações que as macros suportam.

## Como Validar

```bash
source .env
dbt compile --select staging
dbt compile --select intermediate
dbt compile --select marts
```

## Observações

- Não há outras macros versionadas no repositório além das três acima.
- A documentação antiga de macros futuras foi removida para manter o guia alinhado ao código atual.

## Referências

- [Configuração do dbt](dbt_configuration.md)
- [Camada Staging](staging.md)
- [Camada Intermediate](intermediate.md)
- [README do projeto](../README.md)