# Previsão de demanda por produto × loja

**Última atualização:** 19/09/2026 · dados de `dev_lh_nautical` até agosto/2026 · **as 4 etapas concluídas** · análise de crescimento por CD e PDV (§8.12).

Este documento explica, do início ao ponto atual, o trabalho de Machine Learning para prever quanto cada produto vende em cada loja: o problema, como foi pensado para resolver, as análises feitas, os principais achados e como a engenharia de features foi montada.

## Sumário

1. [O problema](#1-o-problema)
2. [Como foi pensado para resolver](#2-como-foi-pensado-para-resolver)
3. [Palavras usadas neste documento](#3-palavras-usadas-neste-documento)
4. [Análises feitas e principais achados](#4-análises-feitas-e-principais-achados)
5. [O método de previsão (a régua)](#5-o-método-de-previsão-a-régua)
6. [Resultados da régua](#6-resultados-da-régua)
7. [Engenharia de features (Etapa 3)](#7-engenharia-de-features-etapa-3)
8. [Modelo de Machine Learning (Etapa 4)](#8-modelo-de-machine-learning-etapa-4)
9. [Decisões tomadas](#9-decisões-tomadas)
10. [Limitações](#10-limitações)
11. [Próximos passos](#11-próximos-passos)
12. [Onde está cada coisa](#12-onde-está-cada-coisa)

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
| **4 · Modelo de Machine Learning** ✅ | Treinar um modelo e comparar com a régua da Etapa 2, tanto por produto × loja quanto por categoria × loja | Notebook `04_modelo_glm_poisson` |

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
| **Centro de Distribuição (CD)** | Um armazém. Nas tabelas é o local com `location_type = warehouse`. São 3: Armazéns Camargo, Novaes e Siqueira |
| **Ponto de Venda (PDV)** | Uma loja. Nas tabelas é o local com `location_type = store`. São 3: Lojas Leão, Mendonça e Oliveira |

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

Recalculada sobre a tabela de features materializada (`ml_features_produto_loja_mes`), a régua final marca **86,6% por produto, 11,9% por categoria × loja, 6,1% por loja e −2,8% de viés** — a pequena diferença no erro por categoria × loja (11,9% contra os 10,7% acima) vem de o notebook 03 ter calculado o índice sazonal em memória, e a tabela dbt o recalcular por corte. **A comparação da Etapa 4 usa a versão da tabela para os dois lados**, de modo que régua e modelo são medidos exatamente na mesma base.

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

Os quatro modelos novos foram checados com `dbt parse` (as referências entre eles resolvem corretamente) e revisados manualmente, linha a linha.

**Atualização (18/09/2026):** as tabelas já estão materializadas em `dev_lh_nautical.ml` e foram lidas de ponta a ponta pela Etapa 4 — 381.581 linhas, 33 colunas, 69 cortes de dezembro/2020 a agosto/2026. A pendência de execução registrada aqui está resolvida.

## 8. Modelo de Machine Learning (Etapa 4)

### 8.1 Objetivo

Treinar um modelo que preveja o total vendido por produto × loja nos 3 meses seguintes e verificar, nas mesmas condições da Etapa 2, se ele supera a régua. "Mesmas condições" aqui é literal: os mesmos 12 meses de teste, as mesmas métricas e a mesma tabela de features para os dois lados.

### 8.2 O que é um GLM, e por que Poisson e Tweedie

Uma **regressão linear** comum supõe que o valor previsto se espalha como uma curva de sino em torno da média e pode assumir qualquer valor, inclusive negativo. Isso não descreve demanda: não existe venda negativa, e 48% das nossas linhas valem exatamente zero.

Um **Modelo Linear Generalizado (GLM)** mantém a ideia de somar efeitos, com duas mudanças:

1. A previsão passa por uma função que a mantém sempre positiva — aqui a exponencial, o chamado **link log**. Como consequência, os efeitos viram **multiplicativos**: cada feature aumenta ou reduz a previsão por um fator, em vez de somar unidades a ela.
2. Escolhe-se uma **família** que descreva como os valores se espalham em torno da média.

**Poisson** é a família natural para contagens — quantas unidades foram vendidas. Supõe que a variância é igual à média.

**Tweedie** é uma família mais geral, com um parâmetro a mais, o **power**. A variância passa a ser `média^power`. Com `power` entre 1 e 2 ela descreve exatamente uma mistura de **muitos zeros exatos** com **valores positivos** — o formato da nossa demanda. `power = 1` é o próprio Poisson; `power = 2` seria a distribuição Gama, que não admite zeros. Quanto maior o power, mais o modelo relativiza as observações de valor alto e mais encolhe as previsões.

Ambas são pertinentes para demanda porque tratam de forma natural as três características que a regressão linear ignora: não-negatividade, excesso de zeros, e variância que cresce junto com o volume.

### 8.3 Como a demanda se distribui

Medido nas 363.419 linhas com alvo conhecido:

| Medida | Valor |
|---|---|
| Observações | 363.419 |
| Mínimo / Máximo | 0 / 55 |
| Média | 4,36 |
| Mediana | 1 |
| Desvio padrão | 5,87 |
| **Variância ÷ média** | **7,90** |
| Proporção de zeros | 48,05% |
| Valores negativos | 0 |
| Valores fracionários | 0 (contagens inteiras puras) |

A razão variância/média de 7,9 indica **superdispersão**: os dados se espalham quase 8 vezes mais do que Poisson pura supõe. Isso **não** descarta Poisson — sob superdispersão o GLM de Poisson continua estimando a média corretamente (o que fica errado é a margem de erro dos coeficientes, que não usamos aqui). Mas justifica testar Tweedie, que deixa o grau de dispersão ser escolhido pelos dados. Por isso as duas famílias foram treinadas e comparadas.

### 8.4 Divisão no tempo

Sem nenhum sorteio de linhas: o recorte é pelo mês de corte.

| Recorte | Cortes | Linhas | Período | Média do alvo | Zeros |
|---|---|---|---|---|---|
| Treino | 30 | 177.282 | 12/2021 – 05/2024 | 3,87 | 51,6% |
| Validação | 12 | 72.648 | 06/2024 – 05/2025 | 4,94 | 43,2% |
| **Teste** | 12 | 72.648 | 06/2025 – 05/2026 | 5,75 | 38,0% |
| Inferência | 3 | 18.162 | 06/2026 – 08/2026 | — | — |

As 40.841 linhas de cortes sem 24 meses de histórico ficam fora do treino: neles a régua e o fator de tendência são nulos, e preenchê-los seria inventar nível. O teste tem exatamente as **72.648 previsões** em que a régua foi medida, o que torna os dois números comparáveis.

A média do alvo cresce 3,87 → 4,94 → 5,75 ao longo dos recortes — o crescimento de ~15% ao ano. **Esse é o principal risco do modelo:** treinado no passado, ele tende a prever abaixo do futuro.

### 8.5 A régua como ponto de partida, não como feature

A decisão de modelagem mais importante. Com link log, entregar a régua como **offset** significa:

```
previsão = régua × exp(soma dos efeitos aprendidos)
```

O modelo aprende apenas **o quanto corrigir a régua**. Três razões:

1. **A regularização encolhe para o lugar certo.** Quanto mais o modelo é penalizado, mais a previsão se aproxima da régua. Se a régua fosse uma feature comum, o encolhimento levaria à média global — bem pior, e de forma silenciosa.
2. **Resolve a extrapolação de nível.** O fator de tendência e o índice sazonal ficam *dentro* do offset, com expoente 1 garantido, e são recalculados a cada corte. O modelo não precisa extrapolar no tempo.
3. **Os coeficientes ficam legíveis** como "+x% sobre a régua".

O `scikit-learn` não tem parâmetro de offset, só peso de amostra. A equivalência usada é ajustar `alvo ÷ régua` com peso `régua^(2−power)` — exata, não aproximada, por a desviância de Tweedie ser homogênea de grau `2−power`. Para Poisson o peso é a própria régua. Há teste unitário fixando esse expoente, porque errá-lo produz um modelo que treina sem reclamar e sai calibrado errado.

### 8.6 O que o Passo 1 revelou

Antes de usar o offset, testou-se deixar o modelo reencontrar a régua sozinho, com o logaritmo dos três ingredientes como features. A régua é o caso em que os três coeficientes valem 1 e o intercepto vale −log(12).

O modelo **não** reencontrou a régua: os coeficientes saíram 0,47 para o nível do grupo, 1,08 para a estação e **0,10** para a tendência, e o viés no teste piorou de −2,8% para −15,7%.

Isso não é erro de código — há um teste que, alimentando a régua como alvo, recupera (1, 1, 1) e −log(12) com erro de 1e-10. A causa está na estrutura dos dados: **o índice sazonal e o fator de tendência têm um único valor por mês de corte**, ou seja, 30 valores para 177 mil linhas. São indistinguíveis de um efeito de calendário, e o modelo encolhe seus expoentes — perdendo justamente a correção de crescimento.

É a justificativa empírica para fixar a régua como offset em vez de deixá-la ser reaprendida.

### 8.7 Features escolhidas

Regra fixada **antes** de olhar qualquer resultado: um grupo de informação por vez, mantido só se melhorar o erro somado por categoria × loja **ou** o viés em **7 ou mais dos 12 cortes de validação**.

| Passo | O que acrescenta | Cortes com erro menor | Cortes com viés menor | Veredito |
|---|---|---|---|---|
| 2 · régua como offset | recalibração multiplicativa | 7/12 | 7/12 | **Manter** |
| 3 · histórico da própria série | `sum_12m`, `sum_3m`, `produto_locais_avg_12m`, meses com venda, recência, `is_stopped_12m`, tamanho dos grupos | 6/12 | 7/12 | **Manter** |
| 4 · categóricas baratas | `frequency_class`, `location_type`, `region` | 3/12 | 2/12 | Descartar |
| 5 · categóricas caras | `category_name`, `brand_name`, `sale_price` | 5/12 | 7/12 | Descartar |

O passo 5 passaria na regra pelo viés (7/12), mas ele é medido **contra o passo 4**, que foi reprovado — e sem o passo 4 a cadeia se interrompe antes. Como o passo 5 também piora o erro somado em relação ao passo 3 (0,1316 contra 0,1300 na validação), ele sai junto.

**Modelo final: passo 3.** Ficou demonstrado formalmente o que os notebooks 01–03 sugeriam: atributos de produto e loja não acrescentam nada, porque o efeito de categoria × loja **já está dentro da régua**.

Ficaram de fora do treino, por princípio: `sk_product`, `sk_location`, `sku`, `product_name`, `cutoff`, o próprio alvo e as flags que dependem do futuro. `avg_monthly_12m` e `avg_monthly_3m` foram excluídas por serem `sum_12m ÷ 12` e `sum_3m ÷ 3` — colineares exatas sob logaritmo.

**O único nulo legítimo da tabela** é `months_since_last_sale` nas séries que nunca venderam (0,9% do treino). Em vez de imputar, a informação virou duas colunas: a bandeira `nunca_vendeu` e uma recência sentinela fixa de 60 meses, constante definida a priori e portanto sem transporte de informação entre recortes.

### 8.8 Escolha do power do Tweedie

Grid de `power ∈ {1,0; 1,1; 1,3; 1,5; 1,7; 1,9}` × `alpha ∈ {0; 1e-4; 1e-3; 1e-2; 1e-1}`, treinado no treino e pontuado **só na validação**. Critério: erro somado por categoria × loja, com o viés como desempate.

O comportamento previsto se confirmou: **conforme o power sobe, o erro por produto melhora de forma monótona (0,9384 → 0,9375) e o viés piora na mesma marcha (−1,21% → −1,78%)**. O modelo aprende a prever baixo, porque é isso que o erro por produto premia quando metade das linhas é zero — exatamente o defeito que a Etapa 2 já havia rejeitado. Por isso a escolha não usa essa métrica.

Vencedor na validação: **Poisson (power = 1,0), alpha = 0** — empatado com Tweedie `power` 1,1 e 1,3 no erro somado (0,1300) e com o menor viés absoluto. Para a comparação no teste manteve-se também o melhor Tweedie (`power = 1,3`).

A dispersão de Pearson medida no treino confirma o diagnóstico: 7,00 sob Poisson e 4,82 sob Tweedie `power` 1,3.

### 8.9 Resultados no teste

12 cortes de 06/2025 a 05/2026, 72.648 previsões, leitura única do teste com a configuração já congelada.

| Modelo | Parâmetros | MAE | RMSE | WAPE produto | WAPE categoria × loja | WAPE loja | Viés |
|---|---|---|---|---|---|---|---|
| Régua (Etapa 2) | — | 4,98 | 6,38 | 86,57% | 11,91% | 6,09% | −2,75% |
| **GLM Poisson** | power=1, alpha=0 | 5,01 | 6,38 | 87,00% | **11,77%** | 6,18% | **+0,12%** |
| GLM Tweedie | power=1,3, alpha=0 | 5,00 | 6,38 | 86,98% | **11,77%** | 6,13% | **−0,05%** |

Ambos os GLM batem a régua em **7 dos 12 cortes** no erro somado e em **8 dos 12** no viés.

**Leitura:** o modelo **empata** com a régua no erro e **elimina o viés** dela. MAE e RMSE são praticamente idênticos nos três casos. O ganho real está no viés: a régua prevê 2,8% abaixo do que se vende, e o GLM erra por 0,1%. Em decisão de compra, um viés de −2,8% significa comprar sistematicamente menos do que se vende, trimestre após trimestre — corrigir isso vale mais do que a terceira casa decimal do erro.

Poisson e Tweedie ficam empatados. Escolheu-se **Poisson** por ser o modelo mais simples, com um parâmetro a menos, e por ter sido o vencedor na validação.

### 8.10 Diagnósticos

**Por faixa de demanda — o achado mais importante:**

| Venda real nos 3 meses | Linhas | Vendido (média) | Previsto pelo GLM (média) |
|---|---|---|---|
| zero | 27.584 | 0,00 | 4,96 |
| 1–2 | 5.083 | 1,50 | 5,80 |
| 3–6 | 11.820 | 4,58 | 5,89 |
| 7–15 | 21.210 | 9,99 | 6,27 |
| 16+ | 6.951 | 20,76 | 7,15 |

A venda real varia de 0 a 20,8 entre as faixas; a previsão varia apenas de 5,0 a 7,2. **O modelo prevê quase o mesmo número para todo produto.**

Isso não é defeito do GLM, e sim a consequência direta do achado do notebook 03. Se o histórico de um produto não informa quanto ele vai vender, não existe informação disponível para separar, *no momento da previsão*, quem venderá 0 de quem venderá 20. O melhor palpite para ambos é o nível do grupo. É também a explicação de por que o erro por produto é 87% e o erro somado por categoria × loja é 12%: os acasos individuais se cancelam ao somar.

**Por loja e por categoria:** resultado misto e de diferenças pequenas — o GLM erra menos em 3 dos 6 locais e a régua nos outros 3 —, mas o viés do GLM é menor em quase todos. Nenhum segmento fica visivelmente pior com o modelo.

**Robustez do recorte:** o corte de treino 05/2024 tem alvo 06–08/2024, que se sobrepõe à janela dos primeiros cortes de validação. Repetindo tudo com 3 meses de embargo no fim do treino (159.126 linhas em vez de 177.282), o resultado no teste não muda: erro por categoria × loja de 11,77% nos dois casos, viés de +0,07% contra +0,12%. A sobreposição é imaterial.

### 8.11 Previsão dos próximos 3 meses

O modelo prevê o **total** dos 3 meses, porque foi assim que o alvo foi definido na Etapa 1. A repartição mês a mês usa os três índices sazonais já presentes na tabela, calculados em cada corte só com o passado:

```
previsão do mês k = total previsto × índice do mês k ÷ (índice1 + índice2 + índice3)
```

O denominador é recalculado a partir dos três índices, e não lido da coluna `season_sum_next_3m`, que vem arredondada — assim os três meses somam exatamente o total previsto (diferença máxima conferida: 0,0). Como os índices dos três meses são diferentes, as três previsões também são: não é o total dividido por três.

**Validação da repartição:** confrontando 217.944 linhas mensais previstas com a venda real mês a mês, o erro **não cresce** ao longo do horizonte — 19,78%, 19,62% e 19,70% por categoria × loja para o primeiro, segundo e terceiro mês. O perfil sazonal usado para repartir se sustenta.

**A entrega**, a partir do corte de agosto/2026, para as 6.054 combinações produto × loja:

| Mês previsto | Séries | Total previsto | Média por série |
|---|---|---|---|
| Setembro/2026 | 6.054 | 8.620,6 | 1,42 |
| Outubro/2026 | 6.054 | 13.269,9 | 2,19 |
| Novembro/2026 | 6.054 | 16.358,7 | 2,70 |
| **Trimestre** | **6.054** | **38.249,2** | **6,32** |

Nenhuma previsão negativa e nenhuma nula. O crescimento de setembro para novembro é o índice sazonal entrando na alta temporada.

### 8.12 Crescimento da demanda por Centro de Distribuição e Ponto de Venda

**Objetivo:** responder à pergunta do time — *qual centro de distribuição e qual ponto de venda têm o maior crescimento de demanda nos três meses previstos?* — a partir da entrega do §8.11.

**Resposta curta:** dentro dos três meses previstos, o CD que mais cresce é o **Armazém Camargo** (+1.338 unidades de setembro para novembro) e o PDV é a **Loja Oliveira** (+1.295). Mas o crescimento **percentual é o mesmo nas seis unidades — 89,8%** —, porque a repartição mensal usa um único perfil sazonal; dentro do horizonte, "quem mais cresce" é "quem tem mais volume". Comparando o trimestre previsto com o mesmo trimestre **realizado em 2025**, que retira a estação da conta, o CD que mais cresce passa a ser o **Armazém Novaes** (+9,6%) e o PDV continua sendo a **Loja Oliveira** (+31,5%).

**Metodologia.** Fonte: `ml_forecast_demanda_mensal`, partição `glm_poisson` (o modelo final), corte de agosto/2026 — 18.162 linhas, uma por produto × local × mês, validadas antes de qualquer soma (um único corte, sem nulos, negativos ou duplicatas, três horizontes em toda série). CD e PDV vêm de `dim_locations.location_type` (`warehouse` / `store`); a tabela mensal não traz o tipo, então o cruzamento é por `sk_location`. Para cada unidade `u`, `D_u(k)` é a soma da demanda prevista de todos os produtos no mês `k`:

```
variação 1→2     = D(2) − D(1)        e em %:  (D(2) / D(1) − 1) × 100
variação 2→3     = D(3) − D(2)
crescimento 1→3  = D(3) − D(1)        ← resposta principal (em unidades)
frente a 2025    = previsto set+out+nov/2026 − realizado set+out+nov/2025   ← complementar
```

O ranking oficial usa o crescimento em **unidades**: é o que foi pedido, e o percentual infla quem parte de base pequena (aqui ele nem sequer discrimina). Crescimento não é demanda acumulada — somar os três meses mede volume. O realizado vem de `ml_complete_monthly_demand`, que exclui meses parciais.

**Período:** setembro, outubro e novembro de 2026 (mês 1, 2 e 3). Referência complementar: setembro a novembro de 2025.

**Os locais e o vínculo PDV → CD.** Não existe nos dados nenhuma coluna ou tabela que diga qual armazém abastece qual loja (`stock_movements` só registra venda, compra e devolução, sem origem e destino). O vínculo abaixo é uma **hipótese de proximidade geográfica** — armazém da mesma UF; se não houver, da mesma região:

| Local | Tipo | UF | Região | CD associado | Critério |
|---|---|---|---|---|---|
| Armazém Camargo | CD | PR | Sul | — | — |
| Armazém Novaes | CD | PI | Nordeste | — | — |
| Armazém Siqueira | CD | AP | Norte | — | não abastece nenhum PDV |
| Loja Leão | PDV | PR | Sul | Armazém Camargo | mesma UF |
| Loja Mendonça | PDV | PI | Nordeste | Armazém Novaes | mesma UF |
| Loja Oliveira | PDV | AL | Nordeste | Armazém Novaes | mesma região |

**Centro de Distribuição — demanda prevista em cada um dos três meses (unidades):**

| CD | Set/2026 | Out/2026 | Nov/2026 | Var. 1→2 | Var. 2→3 | Cresc. 1→3 | Cresc. % | Rank |
|---|---|---|---|---|---|---|---|---|
| **Armazém Camargo** | 1.490,1 | 2.293,7 | 2.827,6 | +803,6 (+53,9%) | +533,9 (+23,3%) | **+1.337,6** | 89,8% | 1 |
| Armazém Novaes | 1.439,9 | 2.216,5 | 2.732,5 | +776,6 (+53,9%) | +515,9 (+23,3%) | +1.292,5 | 89,8% | 2 |
| Armazém Siqueira | 1.391,7 | 2.142,3 | 2.640,9 | +750,6 (+53,9%) | +498,7 (+23,3%) | +1.249,2 | 89,8% | 3 |

**Ponto de Venda — demanda prevista em cada um dos três meses (unidades):**

| PDV | CD associado | Set/2026 | Out/2026 | Nov/2026 | Var. 1→2 | Var. 2→3 | Cresc. 1→3 | Cresc. % | Rank |
|---|---|---|---|---|---|---|---|---|---|
| **Loja Oliveira** | Armazém Novaes | 1.443,2 | 2.221,6 | 2.738,7 | +778,4 (+53,9%) | +517,1 (+23,3%) | **+1.295,5** | 89,8% | 1 |
| Loja Mendonça | Armazém Novaes | 1.435,9 | 2.210,3 | 2.724,8 | +774,4 (+53,9%) | +514,5 (+23,3%) | +1.288,9 | 89,8% | 2 |
| Loja Leão | Armazém Camargo | 1.419,8 | 2.185,5 | 2.694,2 | +765,7 (+53,9%) | +508,7 (+23,3%) | +1.274,4 | 89,8% | 3 |

**Leitura:** o Armazém Camargo e a Loja Oliveira lideram, mas por margens pequenas — 88 unidades entre o primeiro e o terceiro CD, 21 entre a primeira e a terceira loja, num trimestre de mais de 6.000 unidades por local. E o percentual é idêntico em todas: **89,76%**. Isso não é coincidência, é construção. O §8.11 reparte o total de 3 meses pelos índices sazonais da tabela de features, e esses índices são os mesmos para todas as séries de um corte (índice sazonal geral, decisão da Etapa 2). Então, para qualquer unidade, `D(3)/D(1) = índice₃/índice₁ = 1,898`, e o crescimento em unidades é o volume previsto vezes uma constante. **O ranking acima é o ranking de volume previsto** — legítimo como resposta, mas não diz onde a demanda acelera mais. A subida de 53,9% e depois 23,3% é a alta temporada chegando, igual em todo lugar.

**Crescimento frente ao mesmo trimestre de 2025** — a comparação em que a estação não manda:

| Unidade | Tipo | Realizado set–nov/2025 | Previsto set–nov/2026 | Crescimento | Cresc. % | Rank |
|---|---|---|---|---|---|---|
| **Armazém Novaes** | CD | 5.829 | 6.388,9 | **+559,9** | **+9,6%** | 1 |
| Armazém Camargo | CD | 6.179 | 6.611,5 | +432,5 | +7,0% | 2 |
| Armazém Siqueira | CD | 5.945 | 6.174,9 | +229,9 | +3,9% | 3 |
| **Loja Oliveira** | PDV | 4.869 | 6.403,5 | **+1.534,5** | **+31,5%** | 1 |
| Loja Mendonça | PDV | 5.394 | 6.371,0 | +977,0 | +18,1% | 2 |
| Loja Leão | PDV | 5.374 | 6.299,4 | +925,4 | +17,2% | 3 |

Aqui os locais se separam: de +3,9% a +31,5%. Nenhuma unidade cai. O CD vencedor muda porque o Camargo já vendia muito em set–nov/2025, e o salto relativo é menor; as lojas crescem mais que os armazéns pelo mesmo motivo — venderam menos em 2025 e a régua (média do grupo nos últimos 12 meses, corrigida por tendência) atribui a todas um nível parecido para 2026. Frente a 2025, os rankings absoluto e percentual coincidem; dentro do horizonte, o ranking percentual é um empate entre as seis unidades.

**Produtos responsáveis pelo crescimento.** Frente a 2025, o crescimento é **difuso**: no Armazém Novaes os 10 produtos que mais contribuem respondem por 13% dos +560 (são precisos 41 para chegar à metade); na Loja Oliveira, top 10 = 5% dos +1.535 e 113 produtos fazem metade. Os maiores "contribuintes" são todos produtos que **não venderam nada em set–nov/2025** e recebem ~7 unidades de previsão — o nível médio do grupo. É a limitação do §10 aparecendo: o modelo quase não diferencia produtos, então quem vendeu zero "cresce" até a média. A leitura útil é por categoria: no Novaes o crescimento vem de GPS & Plotters (22%), Motores (20%), Sonares e Transdutores (19%), Baterias (17%) e Instrumentos de Navegação (15%), com Pintura Marítima (−58) e Velas (−23) em queda; na Oliveira, de Instrumentos de Navegação (13%), GPS & Plotters (11%), Âncoras (10%), Velas (10%) e Sonares (9%), com todas as 12 categorias subindo. Nenhuma categoria domina.

**Robustez:** o GLM Tweedie (`power` 1,3), que empatou com o Poisson no teste, aponta os mesmos vencedores nas duas definições — Camargo +1.336 e Oliveira +1.294 dentro do horizonte; Novaes +9,5% e Oliveira +31,4% frente a 2025.

**Gráficos** (no notebook 05): evolução realizado + previsto por CD e por PDV, jun/2025 a nov/2026; ranking do crescimento em unidades com o percentual ao lado de cada barra; crescimento % frente a 2025 por unidade; decomposição do crescimento por categoria nos dois vencedores.

**Limitações desta análise:** (1) o vínculo PDV → CD é hipótese geográfica, não dado; (2) o crescimento percentual dentro do horizonte não discrimina por construção; (3) a previsão por local é quase uniforme, porque a régua fixa o nível por categoria × local e o modelo corrige pouco — diferenças pequenas entre unidades não devem ser lidas como sinal; (4) o realizado de 2025 tem a mesma cara de dado simulado que o resto do projeto (§10).

### 8.13 Onde ficam os resultados

Duas tabelas Delta em `dev_lh_nautical.ml`, particionadas por `model_name` e gravadas com `replaceWhere`, de forma que reexecutar um modelo substitui só as linhas dele — a Regressão Linear e o XGBoost dos colegas podem conviver nas mesmas tabelas:

| Tabela | Conteúdo | Linhas por modelo |
|---|---|---|
| `ml_forecast_demanda_3m` | Total de 3 meses por série × corte, com a régua e o alvo real ao lado | 90.810 (teste + inferência) |
| `ml_forecast_demanda_mensal` | A entrega mês a mês: produto, loja, mês previsto, demanda prevista, modelo | 18.162 (6.054 × 3) |

Para reproduzir fora do notebook:

```
PYTHONPATH=. python -m src.analytics_ai.run_demand_glm --model-name glm_poisson
```

---

## 9. Decisões tomadas

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
| **Etapa 4:** régua como offset do GLM | Régua como feature comum | Com link log o modelo aprende só a correção sobre a régua, e qualquer encolhimento leva de volta a ela em vez de à média global |
| **Etapa 4:** Poisson como modelo final | Tweedie `power` 1,3 | Empataram no teste; Poisson tem um parâmetro a menos e venceu na validação |
| **Etapa 4:** descartar as features categóricas | Manter categoria, marca, região | Reprovadas na regra dos 7/12 cortes — o efeito de categoria × loja já está dentro da régua |
| **Etapa 4:** bandeira `nunca_vendeu` + sentinela fixa | Imputar a recência com média ou mediana | Imputar fabricaria histórico; a constante a priori não transporta informação entre recortes |
| **Etapa 4:** escolher pelo erro somado, com viés de desempate | Escolher pelo erro por produto | Subir o `power` melhora o erro por produto e piora o viés — premiar isso é premiar prever abaixo do real |
| **Etapa 4:** repartir o total de 3 meses pelos índices sazonais | Prever cada mês em separado; dividir o total por três | Mantém a comparação com a régua no alvo original e produz três meses diferentes entre si |
| **Crescimento por CD/PDV:** ranking pelo crescimento em unidades (mês 3 − mês 1), com a comparação a set–nov/2025 ao lado | Ranquear só pelo percentual | O percentual dentro do horizonte é o mesmo em todas as unidades (índice sazonal geral) e, em geral, infla quem parte de base pequena |
| **Crescimento por CD/PDV:** vínculo PDV → CD por UF, senão por região | Não relacionar loja a armazém | Não há dado de abastecimento; a hipótese geográfica é declarada e conferível na tabela do §8.12 |

## 10. Limitações

- **Dados com cara de simulados:** todo produto em todo local, locais com o mesmo volume, mesma estação e crescimento em todas as categorias — um padrão bem mais regular do que negócio real costuma ter.
- **Erro por produto sozinho é alto (86,6%)** por causa do acaso da venda; a previsão por produto é um valor esperado com limites, não um valor exato.
- **Limites acertam um pouco menos na alta temporada** (86% a 88% no limite de 9 em 10, contra ~90% esperado).
- **Cadastro de produtos:** o mesmo nome aparece em SKUs diferentes, e há nomes inválidos no cadastro. A previsão usa o SKU, então isso não afeta o resultado, mas atrapalha a leitura.
- **Ambiente:** resultados só validados em desenvolvimento (`dev_lh_nautical`).
- **O modelo quase não diferencia produtos (Etapa 4):** a previsão varia de 5 a 7 unidades enquanto a venda real varia de 0 a 21. Não é defeito do GLM — é a ausência de informação que separe, antes da venda, quem venderá 0 de quem venderá 20. Melhorar isso exige dado novo (preço praticado, promoção, campanha, ruptura de estoque), não algoritmo mais sofisticado.
- **A repartição mensal herda o índice sazonal geral:** como a estação é a mesma para todas as categorias (decisão da Etapa 2), a quebra mês a mês supõe o mesmo perfil sazonal em todo o catálogo. O erro medido não cresce ao longo dos 3 meses, mas a suposição existe.
- **Sobreposição na fronteira dos recortes:** o último corte de treino tem alvo que invade a validação. Medido com 3 meses de embargo, o efeito é imaterial (11,77% nos dois casos), mas o recorte principal não aplica embargo.
- **O crescimento percentual dentro do horizonte é igual em todas as unidades (89,8%):** consequência direta do índice sazonal geral. O ranking de crescimento por CD/PDV no horizonte equivale ao ranking de volume previsto; a comparação com o mesmo trimestre do ano anterior é a que discrimina.
- **O vínculo PDV → CD é uma hipótese:** nenhuma tabela registra qual armazém abastece qual loja; o §8.12 usa proximidade geográfica (UF, depois região).
- **O ganho do modelo está no viés, não no erro:** quem esperar uma queda grande do erro de previsão vai se decepcionar. O que o GLM entrega é uma previsão sem viés sistemático e a quebra mês a mês.

## 11. Próximos passos

**Depois da Etapa 4:**

- **Comparar os três modelos do time** — GLM (este documento), Regressão Linear e XGBoost — no mesmo recorte e nas mesmas métricas. As tabelas `ml_forecast_demanda_3m` e `ml_forecast_demanda_mensal` são particionadas por `model_name` justamente para isso: cada modelo grava a sua partição sem tocar nas outras.
- **Recalibrar os limites de venda (`q_75`, `q_90`) a partir do GLM**, já que a previsão central mudou e o viés saiu.
- **Buscar informação que hoje falta**, que é o único caminho para diferenciar produtos: preço praticado no período, promoções, campanhas e ruptura de estoque.
- **Registrar o modelo** em MLflow / Unity Catalog, se o time decidir versionar modelos além de versionar código.

**Outras pendências:**

- Calibrar os limites de venda separadamente para a alta temporada.
- Corrigir o cadastro de nomes de produto na origem.
- Validar os resultados, no futuro, em dados reais de produção.

## 12. Onde está cada coisa

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
| `notebooks/ml/04_modelo_glm_poisson.ipynb` | **Etapa 4:** escada de features, Poisson × Tweedie, teste final, diagnósticos e a previsão dos 3 meses |
| `src/analytics_ai/demand_glm.py` | Recorte temporal, offset, treino, previsão, repartição mensal e seleção de hiperparâmetros (pandas puro, sem Spark) |
| `src/analytics_ai/demand_predictions.py` | Leitura das features e gravação das tabelas de previsão no Unity Catalog |
| `src/analytics_ai/run_demand_glm.py` | Execução ponta a ponta fora do notebook |
| `tests/test_demand_glm.py` | Testes do offset, do recorte, da repartição mensal e dos contratos de métrica |
| `notebooks/ml/05_crescimento_cd_pdv.ipynb` | Crescimento da demanda prevista por CD e PDV: trajetória nos 3 meses, comparação com 2025, produtos e categorias, robustez com o Tweedie |
| `src/analytics_ai/demand_growth.py` | Validação da tabela mensal, vínculo PDV → CD, fórmulas de crescimento e contribuições (pandas puro, sem Spark) |
| `tests/test_demand_growth.py` | Testes das fórmulas de crescimento, do vínculo, dos casos de borda e da propriedade do índice único |
| `dev_lh_nautical.ml.ml_forecast_demanda_3m` | Previsão do total de 3 meses, com a régua e o alvo real ao lado |
| `dev_lh_nautical.ml.ml_forecast_demanda_mensal` | **A entrega:** previsão mês a mês por produto × loja |

**Para atualizar os números deste documento:** rodar o job de transformação, executar os notebooks 01, 02, 03, 04 e 05 nessa ordem, e revisar o conteúdo acima.
