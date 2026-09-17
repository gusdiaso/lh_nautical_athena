# Modelo ML
Este documento registra a analise da branch `feature/modelo-de-ml`, commit
`942d1e5e02c93a6d1dae36bf3adb80a240d2dd14`. Nenhuma alteracao de codigo ou de
pipeline e necessaria para usar este documento.

## O que existe na branch

A branch cria duas tabelas dbt de apoio em `src/dbt/models/ml/`:

- `agg_demand_daily`: uma linha por produto, localizacao e dia;
- `agg_demand_weekly`: uma linha por produto, localizacao e semana iniciada na segunda-feira.

A demanda usa `quantity_ordered` de pedidos confirmados ou pagos. A serie e
densificada: dias sem venda recebem zero desde o primeiro dia ativo da
combinacao. Membros tecnicos de produto e localizacao sao excluidos.

Tambem existe o notebook
`notebooks/ml/01_planejamento_regressao_linear_zero_inflacao.ipynb`, que faz
diagnostico exploratorio de zeros e planeja a escolha do modelo. Ele nao treina
um modelo; features temporais e a decisao final do algoritmo continuam em aberto.

## O que falta definir

Antes de implementar treino ou inferencia, documentar:

1. unidade de previsao, por exemplo produto x localizacao x dia;
2. horizonte de previsao;
3. data de corte da observacao;
4. regra de treino, validacao e teste temporal;
5. metricas e baseline de comparacao.

Features historicas devem usar somente eventos anteriores ao corte. O mesmo
periodo nao pode ser usado simultaneamente para construir uma feature e medir
o target correspondente.

## Recomendacao para o Gustavo

1. Escolher diaria ou semanal com base em um baseline simples.
2. Fixar a unidade de previsao, o horizonte e a regra de pedidos validos.
3. Criar features temporais somente depois de fixar o cutoff.
4. Comparar regressao linear com um baseline de media movel ou ultimo valor.
5. Usar divisao temporal treino, validacao e teste; nao usar split aleatorio.
6. Registrar metricas, periodo dos dados e versao do dataset.

## Fontes e validacao

As tabelas usam `fact_order_items`, `dim_date`, `dim_products` e
`dim_locations`. Os YAMLs da branch verificam unicidade por chave composta,
relacionamentos, nulidade e demanda nao negativa.

Para validar a branch, execute primeiro `dbt parse`, depois `dbt run --select ml`
e `dbt test --select ml`. O ambiente local requer as variaveis de
`profiles.yml`, incluindo `DBT_HTTP_PATH` e o token do target selecionado.

## Riscos conhecidos

- A densificacao ate o ultimo dia global pode gerar muitas linhas e custo alto.
- Pedidos confirmados ou pagos precisam ter uma regra de negocio validada para
	evitar contar estados inconsistentes.
- Lags e medias moveis podem vazar o target se nao respeitarem o cutoff.
- As tabelas de demanda sao fundacao de features, nao um modelo treinado.
