# XGBoost para demanda produto × loja

**Última atualização:** 20/09/2026 · dados de `dev_lh_nautical` até agosto/2026 · **não supera a régua** no teste.

Este documento descreve o modelo XGBoost da Etapa 4 do projeto de [previsão de demanda](previsao_demanda_produto_loja.md): o que ele prevê, como é treinado e avaliado, o que foi comparado, o resultado e como reexecutar. A análise completa, com gráficos, está em `notebooks/ml/07_modelo_xgboost.ipynb`. O contexto do problema, a régua de comparação e os demais modelos (regressão linear e GLM) estão no documento principal.

## Sumário

1. [Escopo](#1-escopo)
2. [Recorte no tempo](#2-recorte-no-tempo)
3. [O que foi comparado](#3-o-que-foi-comparado)
4. [Resultado](#4-resultado)
5. [Execução](#5-execução)
6. [Saídas](#6-saídas)
7. [Dependências e testes](#7-dependências-e-testes)
8. [Limitações](#8-limitações)

---

## 1. Escopo

O modelo lê a tabela `ml.ml_features_produto_loja_mes` (grão produto × loja × mês de corte, ver o [dicionário de features](dicionario_features_ml_produto_loja_mes.md)) e prevê `target_3m`, a demanda dos **três meses seguintes** ao corte. O objetivo de treino é o de contagem de Poisson (`count:poisson`), o mesmo raciocínio do GLM: demanda não é negativa e mais da metade das linhas vale zero.

Cada resultado é medido contra a régua (`baseline_pred_categoria_local_idx_trend`) nas mesmas linhas, com as métricas compartilhadas de `demand_common.py`: erro por produto × loja, por categoria × loja e por loja (WAPE), e viés.

## 2. Recorte no tempo

Sem nenhum sorteio de linhas, e com **embargo de 3 meses** antes de cada bloco: o alvo de um corte só é conhecido 3 meses depois, então treinar com ele antes disso seria espiar o futuro.

| Bloco | Cortes | Uso |
|---|---|---|
| Treino | Todos os cortes elegíveis até 3 meses antes da validação | Ajusta os candidatos |
| Validação | 6 cortes, imediatamente antes do teste | **Único lugar** onde se escolhe features, hiperparâmetros e calibração |
| Teste | 12 cortes (06/2025 a 05/2026), os mesmos da régua e dos outros modelos | Lido uma vez, com a configuração congelada. O modelo é treinado de novo até 3 meses antes do teste |
| Inferência | Corte mais recente, sem alvo completo | Previsão de verdade; o modelo é treinado com tudo que já tem alvo conhecido |

"Elegível" significa alvo completo (`is_target_complete`) e tendência disponível (`trend_ready`, cortes com 24 meses de histórico ou mais).

## 3. O que foi comparado

Features, calibração e variantes foram decididas **só na validação**; os hiperparâmetros vêm de uma busca anterior, fixada em código (ver a linha correspondente).

| Escolha | Alternativas testadas |
|---|---|
| **Conjunto de features** | `modelo_atual` (5: `categoria_local_avg_12m`, `season_sum_next_3m`, `growth_12m`, `trend_factor` e a régua) · `modelo_atual_historico_serie` (+ 7 colunas do histórico da série) · `modelo_atual_historico_outras_lojas` (+ 3 colunas do produto nos outros locais e tamanho do grupo) |
| **Hiperparâmetros** | 12 configurações dirigidas (`PARAMETER_CANDIDATES`: profundidade, peso mínimo por folha, taxa de aprendizado, número de árvores, amostragem e regularização), sem o produto cartesiano completo. A vencedora é a constante `WINNING_PARAMETERS` (profundidade 3, peso mínimo 10, taxa 0,10, 150 árvores, amostragem 0,9, regularização 5). `search_hyperparameters` faz a busca, mas o `run()` **não a executa**: usa a constante. As variantes `base_margin` e duas etapas varrem só 3 configurações |
| **Calibração** | XGBoost puro · fator global · mistura com a régua de 0% a 100% de XGBoost, de 5 em 5 pontos |
| **Reconciliação** | Redistribui o total da régua por categoria × loja × corte, usando as proporções do XGBoost |
| **Alvo residual** | Aprende a diferença entre o alvo e a régua (em logaritmo), com deslocamento escolhido na validação |
| **Régua como `base_margin`** | O análogo do offset do GLM: a régua é o ponto de partida do modelo. Testado com três valores de epsilon |
| **Duas etapas** | Um classificador estima a probabilidade de vender e um regressor a quantidade quando vende; a previsão é o produto dos dois |

A calibração é escolhida pela soma do erro por categoria × loja, do erro por loja e do valor absoluto do viés. Já a escolha entre conjuntos de features e entre as variantes usa uma pontuação que soma também o erro por produto × loja.

## 4. Resultado

No teste (12 cortes, 72.648 previsões), a variante escolhida na validação (**XGBoost calibrado**) **não supera a régua**:

| Medida | XGBoost calibrado | Régua |
|---|---|---|
| Erro por produto × loja | 85,9% | 86,6% |
| Erro por categoria × loja | 15,6% | 11,9% |
| Erro por loja | 13,5% | 6,1% |
| Viés | −10,9% | −2,8% |

Por produto × loja o XGBoost parece melhor só porque prevê abaixo do real, defeito que o erro por produto premia. Depois de somar, a régua vence com folga. As outras variantes também perdem no erro somado (erro por categoria × loja no teste):

| Variante | Erro por categoria × loja | Viés |
|---|---|---|
| XGBoost puro | 24,3% | −23,0% |
| **XGBoost calibrado** (escolhido na validação) | **15,6%** | −10,9% |
| Duas etapas | 17,3% | −12,6% |
| `base_margin` | 18,9% | −15,9% |
| Residual | 55,2% | −55,2% |
| Reconciliado | 11,9% | −2,8% |

O reconciliado é idêntico à régua **por construção**: ele redistribui o total da régua entre os produtos, então herda o erro agregado dela e não é uma vitória do modelo.

Leitura:

- a calibração é ajustada nos **6 cortes de validação**, onde o viés fica em 0,0%; no teste ele volta a −10,9%. É compatível com uma demanda que continua crescendo depois da validação (no GLM, a média do alvo sobe de 3,87 no treino para 5,75 no teste), mas a causa exata não foi isolada;
- o achado central do projeto, de que o histórico de um produto não informa quanto ele vai vender, limita o que qualquer modelo consegue separar entre produtos do mesmo grupo.

> **Origem dos números.** Saídas salvas no notebook `07_modelo_xgboost` (execução no Databricks `dev`). O notebook se apresenta como "Etapa 5" e não compara com GLM nem regressão linear; essa comparação está no documento principal.

## 5. Execução

Com o ambiente Databricks Connect configurado, a partir da raiz do repositório:

```bash
PYTHONPATH=. python -m src.analytics_ai.run_demand_xgboost \
  --test-output previsoes_teste_xgboost_offset_duas_etapas.csv \
  --forecast-output previsoes_atuais_xgboost_offset_duas_etapas.csv \
  --metrics-output metricas_xgboost_offset_duas_etapas.csv \
  --search-output busca_validacao_xgboost_offset_duas_etapas.csv
```

Os quatro argumentos são opcionais (os nomes acima são o padrão). O runner exige **quatro nomes distintos** e recusa os nomes de arquivos de execuções anteriores (`previsoes_teste.csv`, `previsoes_atuais.csv`, `previsoes_teste_calibradas.csv`, `previsoes_atuais_calibradas.csv`, `comparacao_calibracao_validacao.csv`), para não sobrescrever resultados que já existem.

O acesso remoto usa o perfil Databricks definido em `DATABRICKS_PROFILE` (padrão `lh_nautical_developers`) ou o Runtime do Databricks. Credenciais e arquivos `.env` não fazem parte do versionamento do modelo.

## 6. Saídas

Diferentemente do GLM, o XGBoost **não grava nas tabelas Delta** `ml_forecast_demanda_3m` e `ml_forecast_demanda_mensal`; o runner produz quatro arquivos CSV, na pasta de execução:

| Arquivo (padrão) | Conteúdo |
|---|---|
| `previsoes_teste_xgboost_offset_duas_etapas.csv` | Previsões de todas as variantes nos 12 cortes de teste, com a régua e o alvo real ao lado |
| `previsoes_atuais_xgboost_offset_duas_etapas.csv` | Previsão do corte mais recente (inferência), total de 3 meses por produto × loja |
| `metricas_xgboost_offset_duas_etapas.csv` | Métricas de validação e de teste de cada variante e de cada régua de média móvel |
| `busca_validacao_xgboost_offset_duas_etapas.csv` | Resultado das buscas feitas na validação: `base_margin`, duas etapas e deslocamento residual |

Os CSVs **não estão no `.gitignore`**: confira o `git status` antes de versionar.

## 7. Dependências e testes

Instale as dependências de `requirements.txt`, que fixa `xgboost==3.0.5`, e execute a partir da raiz:

```bash
python -m pytest -q tests/test_demand_xgboost.py tests/test_run_demand_xgboost.py
```

Os testes são offline e não usam Databricks. O pipeline de CI roda `pytest tests/` inteiro.

## 8. Limitações

- **Não supera a régua**, e o motivo é a ausência de informação que separe produtos, não o algoritmo. Melhorar exige dado novo (preço praticado, promoção, campanha, ruptura de estoque).
- **Validação curta:** 6 cortes contêm cada mês do ano no máximo uma vez, e a calibração é ajustada nela, o que favorece sobreajuste.
- **Não grava nas tabelas de previsão** e não entrega a previsão mês a mês; só o GLM faz as duas coisas.
