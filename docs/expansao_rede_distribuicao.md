# Expansão da rede de distribuição: onde abrir o próximo ponto

Análise que responde: *se a LH Nautical abrisse mais um centro de distribuição (loja ou armazém), em qual UF ele deveria ficar?* O entregável é um notebook de análise (`notebooks/ml/09_expansao_rede_distribuicao.ipynb`) apoiado por três modelos dbt, um seed de coordenadas e um módulo Python testado offline.

## 1. O que a análise concluiu

Números da execução em `dev_lh_nautical`, janela de 12 meses completos (set/2025 a ago/2026).

| Achado | Valor |
|---|---|
| Distância média real até a unidade que atendeu | **1.657 km** |
| Distância média se cada pedido saísse da unidade mais próxima | **636 km** (−62%) |
| Unidades vendidas que saíram da unidade mais próxima | **26,4%** |
| Melhor ponto novo pelo ganho em unidade·km | **RO** (636 → 505 km); AM a 4% de distância (empate técnico) |
| Segundo ponto (seleção gulosa) | **DF** (505 → 402 km); terceiro, RJ (346 km) |
| UFs entre os 5 primeiros nos dois rankings (ganho e score) | RO, AM e DF |
| Tipo recomendado para os candidatos do topo | Armazém, em todos os limites testados |
| Ponto em RO sem mudar o despacho | Distância média **sobe** para 1.731 km |

**Recomendação, em ordem:** (1) despachar pela unidade mais próxima antes de construir; (2) se for abrir um ponto, um armazém no Norte (RO ou AM); (3) segundo ponto no DF; (4) não abrir RO sem mudar o despacho.

O ranking é **direcional**: compara UFs entre si com base em distância em linha reta e volume, sem custo de investimento nem frete real.

## 2. Camadas de dados

| Objeto | Camada | Grão | Papel |
|---|---|---|---|
| `seeds/geo_uf_capital_coordinates.csv` | seed (schema `silver`) | UF | Latitude e longitude da capital das 27 UFs |
| `int_uf_coordinates` | silver | UF | As 27 UFs com coordenada: posição do cliente médio e lista de candidatas |
| `int_location_coordinates` | silver | unidade física | `dim_locations` (sem membro técnico) com a coordenada da capital da UF da unidade |
| `agg_sales_by_customer_state_month` | gold | mês × UF do cliente × unidade de origem × canal | Unidades, receita líquida e lucro estimado, sem pedidos cancelados nem rascunhos |

O prefixo `agg_` segue o padrão de `agg_demand_*`: o modelo é uma **agregação**, não um fato de grão transacional como os `fact_*`. Fica em `marts` (gold) porque é consumo de análise, não feature de Machine Learning.

**Cliente sem UF** cai em `customer_state = 'SEM_UF'`: sai do ranking, mas permanece na tabela para o volume total não ser subestimado. Hoje é 0% das unidades.

**Testes dbt.** `not_null`/`unique` e intervalo geográfico do Brasil no seed; `not_null` em latitude e longitude de `int_location_coordinates`, que reprova o build se uma unidade ficar sem coordenada (o join é `LEFT` de propósito, para a falha aparecer no modelo certo em vez de a unidade sumir); teste singular `int_uf_coordinates_has_27_states`; grão único e `relationships` para `dim_locations` no agregado.

## 3. Módulo `src/analytics_ai/network_expansion.py`

Pandas puro, sem Spark. Funções principais:

| Função | O que faz |
|---|---|
| `preparar_vendas`, `validar_vendas_uf` | Converte `Decimal` em float e valida a forma da tabela (`ValueError` alto, sem NaN silencioso) |
| `haversine_km`, `matriz_uf_uf`, `distancia_uf_local` | Distância em linha reta entre capitais, UF × UF e UF × unidade ativa |
| `distancia_atendimento_atual` | Menor distância de cada UF a uma unidade ativa, geral ou por tipo |
| `distancia_real_de_atendimento`, `participacao_unidade_mais_proxima` | Distância que os pedidos de fato percorreram e fração que saiu da unidade mais próxima |
| `demanda_por_uf`, `crescimento_yoy_por_uf` | Unidades e receita por UF; crescimento 12 meses vs 12 anteriores (NaN, nunca número inflado, sem histórico) |
| `ganho_por_candidato` | Núcleo: ganho em unidade·km de abrir um ponto em cada UF, com fração na própria UF e nº de UFs beneficiadas |
| `selecao_gulosa` | 1º, 2º e 3º pontos, cada um dado os anteriores |
| `classificar_tipo` | Loja, armazém ou ambíguo, com o motivo em texto |
| `ranquear_candidatos`, `frequencia_no_topo` | Ranking por ganho e por score composto (parcelas visíveis) e sua estabilidade a pesos sorteados |

Testes: `tests/test_network_expansion.py` (offline, rodam com `pytest tests/`).

## 4. Hipóteses e limitações

- **Coordenadas.** Os nomes de cidade das unidades em `dim_locations` são fictícios e não existem no IBGE, então a unidade é posicionada na capital da própria UF. Duas unidades na mesma UF ficam a distância zero. Para decidir *entre* UFs é aceitável; para escolher cidade, não.
- **Cliente.** Também representado pela capital da UF do endereço primário. Em estados grandes (AM, PA, MT, MG) a capital pode estar longe da maior parte da demanda.
- **Custo logístico.** Modelado como demanda × km em linha reta. Não há frete, transportadora, data de envio nem de entrega ao cliente: `orders` só registra `placed_at`. O único prazo real na base é fornecedor → unidade, usado só como diagnóstico de saúde das unidades.
- **Um ponto por vez.** O ganho é o de abrir um ponto, sem capacidade, sem custo e sem reação da demanda à nova cobertura. A seleção gulosa aproxima o caso de vários pontos, mas não garante o ótimo conjunto.
- **Despacho.** O ganho supõe que cada pedido sai da unidade mais próxima; hoje só 26,4% saem. O notebook mostra o cenário sem mudança de despacho.
- **Canal.** No PDV (`pos`) os clientes também estão espalhados pelo país (distância média de 1.638 km, igual à do e-commerce); a hipótese de loja física com distância próxima de zero não se confirma nestes dados.
- **Demanda reprimida.** UF mal atendida pode vender menos por isso. Os dados não mostram o efeito (correlação de postos de −0,10 entre distância e unidades), mas com 27 UFs o teste tem pouco poder.
- **Sem investimento.** Não há custo de terreno, obra ou folha: a análise diz onde o ganho logístico é maior, não se ele paga o investimento.

## 5. Como rodar e atualizar

```bash
dbt build --select geo_uf_capital_coordinates+ agg_sales_by_customer_state_month
```

O agregado não depende do seed; por isso o seletor `geo_uf_capital_coordinates+` sozinho **não** o constrói e ele precisa ser nomeado.

Depois, executar `notebooks/ml/09_expansao_rede_distribuicao.ipynb` (localmente com `DATABRICKS_PROFILE` definido, ou no workspace). O notebook lê cinco tabelas uma vez cada e trabalha em pandas.

**Ao abrir uma unidade nova:** se ela ficar em UF já coberta pelo seed (as 27 capitais), nada muda. `int_location_coordinates` falha se a UF não tiver coordenada.

## 6. Onde está cada coisa

| Arquivo | Conteúdo |
|---|---|
| `notebooks/ml/09_expansao_rede_distribuicao.ipynb` | A análise, com gráficos e a recomendação |
| `src/analytics_ai/network_expansion.py` | Distâncias, ganho, seleção gulosa, tipo e ranking |
| `tests/test_network_expansion.py` | Testes offline do módulo |
| `seeds/geo_uf_capital_coordinates.csv`, `seeds/seeds.yml` | Coordenadas das capitais e seus testes |
| `src/dbt/models/intermediate/int_uf_coordinates.*`, `int_location_coordinates.*` | Coordenadas das UFs e das unidades |
| `src/dbt/models/marts/agg_sales_by_customer_state_month.*` | Vendas por UF do cliente e unidade de origem |
| `src/dbt/tests/int_uf_coordinates_has_27_states.sql` | Garante as 27 UFs |
