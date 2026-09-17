# Previsão de demanda por produto × loja

**Última atualização:** 17/09/2026 · dados de `dev_lh_nautical` até agosto/2026 · Etapas 1, 2 e 3 de 4 concluídas.

Este documento explica, do início ao ponto atual, o trabalho de Machine Learning para prever quanto cada produto vende em cada loja: o problema, como foi pensado para resolver, as análises feitas, os principais achados e como a engenharia de features foi montada.

## Sumário

1. [O problema](#1-o-problema)
2. [Como foi pensado para resolver](#2-como-foi-pensado-para-resolver)
3. [Palavras usadas neste documento](#3-palavras-usadas-neste-documento)
4. [Análises feitas e principais achados](#4-análises-feitas-e-principais-achados)
5. [O método de previsão (a régua)](#5-o-método-de-previsão-a-régua)
6. [Resultados da régua](#6-resultados-da-régua)
7. [Engenharia de features (Etapa 3)](#7-engenharia-de-features-etapa-3)
8. [Decisões tomadas](#8-decisões-tomadas)
9. [Limitações](#9-limitações)
10. [Próximos passos](#10-próximos-passos)
11. [Onde está cada coisa](#11-onde-está-cada-coisa)

---

## 1. O problema

A LH Nautical precisa saber, para **cada produto (SKU) em cada uma das suas 6 lojas/armazéns**, quanto vai vender nos **próximos 3 meses** — informação usada para decidir compra e estoque.

Isso dá **6.054 combinações produto × loja** (1.009 produtos × 6 locais) para prever, todo mês, de novo.

O desafio central: a venda de um produto numa loja é **rala**. Um produto típico vende em pouquíssimos meses do ano, e a maioria dos meses não tem venda nenhuma. Prever "quanto vende" quando "quase nunca vende nada" não é um problema trivial — e a forma certa de abordar isso muda dependendo de como os dados realmente se comportam, não de suposições.

Por isso, antes de treinar qualquer modelo de Machine Learning, o trabalho começou entendendo os dados a fundo.

## 2. Como foi pensado para resolver

O trabalho foi dividido em 4 etapas, cada uma dependendo da anterior:

| Etapa | Objetivo | Onde está |
|---|---|---|
| **1 · Conhecer os dados** ✅ | Entender por que a demanda tem tantos zeros, em que granularidade prever, e como as 6.054 séries se distribuem (produtos parecidos? concentração de volume? sazonalidade?) | Notebooks `01_eda_demand_zeros` e `02_distribuicao_produtos` |
| **2 · Criar uma régua de comparação** ✅ | Montar a previsão mais simples possível que já funcione bem, e medir o quanto ela erra. Essa régua vira a "nota mínima" que qualquer modelo de Machine Learning precisa superar para valer a pena existir | Notebook `03_medias_moveis` |
| **3 · Engenharia de features** ✅ | Transformar o que a régua provou funcionar numa tabela de dados (dbt) pronta para alimentar modelos de Machine Learning, sem depender de código Python espalhado | `src/dbt/models/ml/` |
| **4 · Modelo de Machine Learning** ⏳ | Treinar um modelo e comparar com a régua da Etapa 2, tanto por produto × loja quanto por categoria × loja | A fazer |

**Por que essa ordem importa:** pular direto para um modelo de Machine Learning sem as etapas 1 e 2 é arriscado — sem saber como os dados se comportam, é fácil montar features que não fazem sentido, e sem uma régua de comparação não dá para saber se o modelo é realmente bom ou só parece bom.

## 3. Palavras usadas neste documento

| Termo | Significado |
|---|---|
| **Série** | A venda de um produto numa loja, mês a mês. Existem 6.054 séries (1.009 produtos × 6 locais) |
| **Corte** | O mês em que a previsão é feita. Só pode usar informação até esse mês, nunca o futuro |
| **Grupo** | Todos os produtos de uma mesma categoria, num mesmo local. Ex.: os motores da Loja Leão |
| **Média móvel (MM12 / MM3)** | Venda média por mês, olhando os últimos 12 (ou 3) meses |
| **Índice sazonal** | Quanto um mês vende comparado a um mês típico. 1,0 = típico; 1,77 = 77% acima; 0,42 = 58% abaixo |
| **Fator de tendência** | Correção pelo crescimento das vendas. Sem ela, uma média do passado prevê menos do que realmente vai acontecer numa empresa que está crescendo |
| **Régua** | Uma regra de previsão simples, usada como referência. Um modelo de Machine Learning só se justifica se for melhor que ela |
| **Erro (WAPE)** | De cada 100 unidades vendidas, quantas a previsão errou para mais ou para menos. Prever sempre zero já dá 100% de erro |
| **Erro somado** | O erro medido depois de somar as previsões e as vendas de vários produtos (por categoria numa loja, por loja, ou no total). Erros para cima e para baixo se cancelam |
| **Viés** | Se a previsão erra sempre para o mesmo lado. Negativo = a previsão, no total, ficou abaixo do que foi vendido |
| **Limite de venda** | Um teto: "a venda não deve passar disso". Ex.: limite de 9 em 10 = em 9 de cada 10 vezes, a venda real fica até esse valor |
| **Acaso (ruído)** | Variação sem padrão, que não dá para prever — como o resultado de um dado |

## 4. Análises feitas e principais achados

### 4.1 Notebook 01 — Por que a demanda tem tantos zeros, e em que granularidade prever

**Pergunta 1: os zeros são erro de dado?** Não. Foram testadas quatro explicações possíveis, e nenhuma se sustentou:

- Não vêm de produtos que pararam de vender (só 5% dos zeros vêm de séries paradas).
- Não vêm da regra de quais pedidos contam como venda (ela só exclui pedidos cancelados e rascunhos, uma exclusão correta).
- Não vêm de falta de estoque (a chance de não vender é quase igual com e sem estoque em mãos).
- Não se concentram em nenhum grupo específico (toda categoria, todo tipo de loja, tem ~99% de dias sem venda).

**Conclusão:** um produto simplesmente vende pouco. Isso é o próprio negócio, não um problema a corrigir nos dados.

**Pergunta 2: em que granularidade prever, e o quê exatamente?** Foram comparados dia, semana, mês e trimestre, e dois alvos (um mês vs. o total de 3 meses):

| Forma de prever | % de vezes sem venda | Histórico disponível por série |
|---|---|---|
| Dia a dia | 99% | ~2.284 pontos |
| Semana a semana | 94% | ~327 pontos |
| Mês a mês | 79% | ~76 pontos |
| Trimestre fixo | 50% | ~26 pontos, só prevê a partir de jan/abr/jul/out |
| **Total dos 3 meses seguintes, na série mensal** | **50%** | ~71 pontos, prevê a partir de qualquer mês |

**Conclusão:** a série **mensal**, prevendo o **total dos 3 meses seguintes**, é o melhor equilíbrio — corta os zeros pela metade em relação a prever mês a mês, sem perder histórico nem flexibilidade.

### 4.2 Notebook 02 — Como as 6.054 séries se distribuem

- **Volume espalhado, não concentrado:** é preciso 59% dos produtos para chegar a 80% do volume vendido (a famosa "regra 80/20" não se aplica aqui). Não existe um pequeno grupo de produtos "campeões de venda" — a previsão precisa funcionar bem para a maioria, não só para alguns.
- **Um produto típico vende em ~3 dos 12 meses do ano.** Isso já avisa que olhar só os últimos 3 meses de uma série (MM3) vai ser uma péssima régua — na maior parte do tempo, esses 3 meses vão estar zerados.
- **Não há produtos novos nem descontinuados de verdade.** O produto mais recente já tem 39 meses de histórico, e 98% dos produtos que passaram 12 meses sem vender voltaram a vender depois. Ou seja, "parou de vender" não quer dizer "saiu de linha" — é só a demanda naturalmente espaçada desse tipo de produto.
- **Todo produto vende em todos os 6 locais**, e cada local representa uma fatia parecida do volume (16-17%) — nenhuma loja domina o negócio.
- **A estação é igual em todas as categorias** (correlação de 0,985 a 0,995 com a estação geral) — não é preciso um calendário sazonal diferente por categoria.
- **A demanda cresceu ~15% no último ano**, de forma parecida em todas as categorias e locais — e isso vem de cada produto vender mais, não de mais produtos entrando no catálogo.

**Consequência prática:** como o negócio é bastante uniforme (nenhum produto-estrela, nenhum produto morrendo, mesma época de alta venda em todo lugar), dá para tratar as 6.054 séries com o mesmo método, sem regras especiais por tipo de produto.

### 4.3 Notebook 03 — Construção e validação da régua (o achado mais importante)

Esse notebook testou várias formas de prever e chegou ao achado central de todo o projeto:

> **O histórico de um produto não informa quanto ele vai vender.** A correlação entre o quanto um produto vendeu num ano e o quanto vende no ano seguinte é **praticamente zero** (0,003). Os 20% de produtos que **mais** venderam num ano (39,5 unidades em média) venderam **exatamente o mesmo** que os 20% que **menos** venderam (5,9 unidades) no período seguinte: ambos os grupos venderam ~5,8 unidades. Isso é o mesmo efeito de jogar um dado: quem tirou números altos numa rodada não tem mais chance de tirar números altos na próxima.

O que **de fato** prevê a venda de um produto:

1. **O nível do grupo** — a venda média de todos os produtos da mesma categoria, na mesma loja. Prever pela média do grupo erra menos (85,6%) do que prever pelo histórico do próprio produto (93,1%).
2. **A estação do ano** — sem ajustar por isso, a previsão erra de +107% a −39% dependendo da época. Um índice sazonal corrige isso.
3. **A tendência de crescimento** — sem corrigir, qualquer média do passado tende a prever abaixo do real, porque a empresa está crescendo ~15% ao ano.

## 5. O método de previsão (a régua)

A régua final combina os três ingredientes acima:

```
Quantidade esperada = média da categoria no local
                       × índice sazonal (soma dos 3 meses previstos)
                       × fator de tendência
```

Ela entrega, para cada produto × loja:

- a **quantidade esperada** (o número acima);
- um **limite de venda de 3 em cada 4 vezes** (`q_75`) — um teto que a venda real ultrapassa só 25% das vezes;
- um **limite de venda de 9 em cada 10 vezes** (`q_90`) — um teto mais alto, ultrapassado só 10% das vezes.

Os limites existem porque a venda de **um único produto** varia muito ao redor da média esperada (metade dos casos vende zero). Eles foram calculados olhando 24 meses anteriores ao período de teste, e depois validados nos 12 meses de teste mais recentes — sem nunca olhar o futuro.

## 6. Resultados da régua

Testada nos 12 meses mais recentes (72.648 previsões: 6.054 séries × 12 meses), comparando com o que de fato foi vendido:

| Régua | Erro por produto | Erro por categoria × loja | Erro por loja | Viés |
|---|---|---|---|---|
| Média dos últimos 3 meses | 120,5% | 49,5% | 48,7% | −1,9% |
| Média dos últimos 12 meses | 99,2% | 36,3% | 35,5% | −8,1% |
| Média de 12 meses × estação | 93,1% | 14,5% | 12,0% | −11,7% |
| **Régua final: grupo × estação × tendência** | **86,6%** | **10,7%** | **6,1%** | **−2,8%** |

**Por que o erro por produto é tão maior que o erro somado?** Um produto sozinho pode vender 0 ou 20 por puro acaso — ninguém consegue prever isso produto a produto. Mas ao somar vários produtos (por categoria numa loja, ou por loja inteira), quem vendeu mais que o previsto compensa quem vendeu menos, e o erro cai bastante. Por isso a previsão é mais confiável para decisões agregadas (compra de uma categoria, planejamento de uma loja) do que para acertar exatamente um produto isolado.

Os limites de venda também foram conferidos: nos 12 meses de teste, a venda real ficou dentro do limite de 3 em 4 em **75,2%** dos casos e dentro do limite de 9 em 10 em **89,6%** — muito perto do prometido.

**Esses números (10,7% / 6,1% / −2,8% de viés) são a nota mínima que qualquer modelo de Machine Learning precisa superar na Etapa 4.**

## 7. Engenharia de features (Etapa 3)

Com a régua validada, o passo seguinte foi transformar seus ingredientes numa **tabela de dbt** (schema `ml`) pronta para alimentar modelos de Machine Learning — sem depender de código Python fora do pipeline de dados.

**Princípio:** como os produtos não se diferenciam de forma consistente (achado do notebook 03), a tabela de features não tenta descrever cada produto — ela descreve o **grupo**, a **estação** e a **tendência**, que são as três coisas que a régua provou que realmente preveem a venda.

### 7.1 Da tabela diária até a tabela de features

A tabela final é o resultado de uma cadeia de 6 modelos em `src/dbt/models/ml/`:

| # | Modelo | O que faz |
|---|---|---|
| 1 | `agg_demand_daily` | Uma linha por produto × loja × dia, desde a primeira venda daquele produto naquela loja até o último dia com dado no negócio inteiro. Dias sem venda entram como **quantidade zero**, nunca como linha ausente — essencial para que qualquer média móvel calculada depois não tenha buracos escondidos |
| 2 | `agg_demand_monthly` | A mesma série, somada por mês — o grão escolhido no notebook 01 |
| 3 | `ml_complete_monthly_demand` | Remove os meses **parciais** (o primeiro mês de cada produto × loja, e o último mês do negócio inteiro, se estiver cortado ao meio) — a mesma limpeza feita nos notebooks 01-03 |
| 4 | `ml_seasonal_trend` | Para **cada mês do histórico**, recalcula o índice sazonal dos 3 meses seguintes e o fator de crescimento, usando só a venda que já tinha acontecido até aquele mês (nunca o futuro) |
| 5 | `ml_cutoff_panel` | Para cada produto × loja × mês, soma quanto vendeu nos 12 e nos 3 meses anteriores, e soma o alvo (quanto vende nos 3 meses seguintes) |
| 6 | `ml_features_produto_loja_mes` | A tabela final: uma linha por produto × loja × mês, juntando tudo acima com os atributos de produto e loja — pronta para o modelo ler |

### 7.2 O que entra na tabela final, e por quê

| Grupo | Exemplos de colunas | Prioridade | Por quê |
|---|---|---|---|
| **Nível do grupo, estação e tendência** | `categoria_local_avg_12m`, `produto_locais_avg_12m`, `seasonal_index_month_plus1..3`, `season_sum_next_3m`, `growth_12m`, `trend_factor` | **Essencial** | É o que a régua provou que prevê a venda |
| **Histórico da própria série** | `sum_12m`, `sum_3m`, `months_with_sale_12m`, `months_since_last_sale`, `frequency_class` | Testar, provavelmente inútil | O achado do notebook 03 diz que isso não ajuda, mas é o modelo que precisa confirmar com dados, não a intuição |
| **Atributos de produto e loja** | `category_name`, `brand_name`, `sale_price`, `location_name`, `location_type`, `region` | Baixa prioridade | Categorias e locais vendem de forma muito parecida entre si |
| **A própria régua, como feature** | `baseline_pred_categoria_local_idx_trend` | Bônus | Dá ao modelo um ponto de partida forte — ele só precisa aprender a corrigir o que sobra, em vez de reaprender a mesma conta do zero |

A tabela também marca, linha a linha, se aquele corte já tem o alvo completo (`is_target_complete`): `true` são linhas de **treino/avaliação**, `false` são linhas de **inferência** (previsão de verdade, corte recente demais para já se saber o resultado).

### 7.3 Validação

Os quatro modelos novos foram checados com `dbt parse` (as referências entre eles resolvem corretamente) e revisados manualmente, linha a linha. Ainda falta rodar de verdade contra o Databricks (`ml_run` + `ml_test`, ou `dbt build --select ml`) para pegar qualquer erro de sintaxe que só apareça em execução real — não havia credencial disponível no momento em que foram criados.

## 8. Decisões tomadas

| Decisão | Descartado | Motivo |
|---|---|---|
| Manter os meses sem venda | Tratar zeros como erro | São venda baixa real |
| Série mensal, alvo = total dos 3 meses seguintes | Diário, semanal, trimestre fixo | Menos zeros e ruído, sem perder histórico |
| Excluir meses incompletos | — | Distorcem a série |
| Índice sazonal geral (recalculado a cada corte) | Índice fixo por categoria | Mesma estação em todas as categorias |
| Fator de tendência | Médias sem correção | Remove o viés de crescimento |
| Nível pelo grupo (categoria no local) | Média do próprio produto | Produtos não se diferenciam de forma consistente |
| Mesmo método para todos os produtos | Regras especiais para novos e parados | Não há produtos novos; "parados" voltam a vender |
| Entregar quantidade esperada + 2 limites | Um número único; uma faixa "de X a Y" | A venda por produto varia muito; o início de qualquer faixa seria sempre 0 |
| Comparar por erro somado, viés e desvio de Poisson | Erro por produto sozinho | O erro por produto sozinho premia prever abaixo do real |
| Dados simulados tratados como reais | Desconsiderar o exercício | É um desafio — a análise vale como se fosse produção |
| Cor/tamanho/material do produto ficaram de fora da tabela de features | Incluir de imediato | Categoria (mais grosseira) já mostrou pouca diferença; dados existem em `int_variant_attribute_values` se algum dia valer testar |

## 9. Limitações

- **Dados com cara de simulados:** todo produto em todo local, locais com o mesmo volume, mesma estação e crescimento em todas as categorias — um padrão bem mais regular do que negócio real costuma ter.
- **Erro por produto sozinho é alto (86,6%)** por causa do acaso da venda; a previsão por produto é um valor esperado com limites, não um valor exato.
- **Limites acertam um pouco menos na alta temporada** (86% a 88% no limite de 9 em 10, contra ~90% esperado).
- **Cadastro de produtos:** o mesmo nome aparece em SKUs diferentes, e há nomes inválidos no cadastro. A previsão usa o SKU, então isso não afeta o resultado, mas atrapalha a leitura.
- **Ambiente:** resultados só validados em desenvolvimento (`dev_lh_nautical`).

## 10. Próximos passos

**Etapa 4 — Modelo de Machine Learning:**

1. Treinar um primeiro modelo usando só o nível do grupo, a estação e a tendência — ele precisa **empatar** com a régua. Isso confirma que a tabela de features está correta e não usa dados do futuro.
2. Acrescentar um grupo de informação por vez (histórico da própria série, depois atributos) e manter só o que melhorar o erro somado ou o viés na maioria dos 12 meses de teste.
3. Treino e teste sempre separados pelo tempo (`is_target_complete = true` para treinar, nunca sorteando linhas aleatoriamente).
4. **Comparar o resultado do modelo com a régua em dois níveis: produto × loja e categoria × loja** — não só num dos dois, porque o erro por produto sozinho pode enganar.

**Outras pendências:**

- Calibrar os limites de venda separadamente para a alta temporada.
- Corrigir o cadastro de nomes de produto na origem.
- Rodar `ml_run` + `ml_test` no Databricks para validar a sintaxe SQL da tabela de features em execução real.
- Validar os resultados, no futuro, em dados reais de produção.

## 11. Onde está cada coisa

| Arquivo | Conteúdo |
|---|---|
| `notebooks/ml/01_eda_demand_zeros.ipynb` | Diagnóstico dos zeros, escolha da granularidade e do alvo |
| `notebooks/ml/02_distribuicao_produtos.ipynb` | Distribuição das séries: concentração, frequência, produtos novos/parados, estação por categoria, crescimento |
| `notebooks/ml/03_medias_moveis.ipynb` | Persistência entre anos, método da régua, resultados, limites de venda e base de comparação |
| `src/analytics_ai/demand_baselines.py` | Cálculo da régua, dos limites de venda e das métricas de erro |
| `src/analytics_ai/eda_demand_zeros.py`, `eda_demand_distribution.py`, `ml_config.py` | Funções usadas nos notebooks 01 e 02, e nomes das tabelas |
| `src/dbt/models/ml/agg_demand_daily.sql` (e `_weekly`, `_monthly`, `_quarterly`) | Tabelas de demanda por dia, semana, mês e trimestre |
| `src/dbt/models/ml/ml_complete_monthly_demand.sql` | Base sem meses parciais |
| `src/dbt/models/ml/ml_seasonal_trend.sql` | Índice sazonal e tendência, recalculados por corte |
| `src/dbt/models/ml/ml_cutoff_panel.sql` | Janelas de 12/3 meses e alvo, por produto × loja × corte |
| `src/dbt/models/ml/ml_features_produto_loja_mes.sql` | A tabela final de features de Machine Learning |

**Para atualizar os números deste documento:** rodar o job de transformação, executar os notebooks 01, 02 e 03 nessa ordem, e revisar o conteúdo acima.
