# XGBoost para demanda produto × loja

## Escopo

O modelo usa a tabela `ml.ml_features_produto_loja_mes` no grão
`produto × loja × cutoff` e prevê `target_3m`, a demanda dos três meses
seguintes ao corte. As features atuais são as de grupo, sazonalidade,
tendência e a régua `baseline_pred_categoria_local_idx_trend`.

O treinamento é temporal: seis cortes completos são usados para validação e
os 12 cortes completos seguintes ficam reservados para o teste final. O
embargo é de três meses, pois o alvo só fica conhecido após o horizonte.

## Execução

Com o ambiente Databricks Connect configurado:

```bash
python -m src.analytics_ai.run_demand_xgboost \
  --test-output previsoes_teste_xgboost_offset_duas_etapas.csv \
  --forecast-output previsoes_atuais_xgboost_offset_duas_etapas.csv \
  --metrics-output metricas_xgboost_offset_duas_etapas.csv \
  --search-output busca_validacao_xgboost_offset_duas_etapas.csv
```

O script executa as buscas somente na validação e grava previsões, métricas e
resultados de busca em arquivos CSV. Os nomes de saída devem ser novos para
preservar resultados anteriores.

## Dependências e testes

Instale as dependências de `requirements.txt`, incluindo `xgboost==3.0.5`, e
execute:

```bash
python -m py_compile src/analytics_ai/demand_xgboost.py src/analytics_ai/run_demand_xgboost.py
python -m pytest -q unit_tests/test_demand_xgboost.py
```

O acesso remoto usa o perfil Databricks configurado no ambiente local ou no
Runtime do Databricks. Credenciais e arquivos `.env` não fazem parte do
versionamento do modelo.
