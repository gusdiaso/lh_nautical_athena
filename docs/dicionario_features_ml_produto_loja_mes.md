# Dicionário de Features — `ml_features_produto_loja_mes`

> Tabela: `src/dbt/models/ml/ml_features_produto_loja_mes.sql`
> Grão: **uma linha por produto (SKU) × loja × mês de corte**.
> Cada coluna abaixo não foi escolhida de forma arbitrária — é a tradução direta de um achado testado em um dos notebooks `notebooks/ml/01_eda_demand_zeros.ipynb`, `02_distribuicao_produtos.ipynb` ou `03_medias_moveis.ipynb`. A coluna "Origem" aponta o notebook e a seção exata de onde veio a decisão de incluir (ou manter só para teste) cada feature.

---

## 1. Identificadores e chaves

| Coluna | O que representa | Uso no modelo |
|---|---|---|
| `cutoff` | Mês de corte (1º dia do mês) — só entra informação disponível até essa data | Não é feature; usada para split temporal treino/teste |
| `sk_product` | Chave da dimensão de produtos | Não é feature; usada para join |
| `sk_location` | Chave da dimensão de localizações | Não é feature; usada para join |

## 2. Atributos descritivos de produto e loja — baixa prioridade

| Coluna | O que representa | Origem | Por que baixa prioridade |
|---|---|---|---|
| `sku` | Código do produto | Notebook 02, geral | Alta cardinalidade, identificador não generaliza — **excluir do treino** |
| `product_name` | Nome do produto | Notebook 02, geral | Mesmo motivo do `sku` — **excluir do treino** |
| `category_name` | Categoria do produto | Notebook 02 (seções 5 e 8) | Categorias se comportam de forma parecida entre si em volume, sazonalidade e crescimento — também é a chave do nível de grupo categoria × loja |
| `brand_name` | Marca do produto | Notebook 02, geral | Sem evidência de que a marca discrimine o comportamento de venda |
| `sale_price` | Preço de venda do produto | Notebook 02, geral | Atributo de controle, não testado como driver forte |
| `location_name` | Nome da loja/armazém | Notebook 02, geral | Chave do nível de grupo categoria × loja |
| `location_type` | Tipo de local (loja \| armazém) | Notebook 02, geral | Locais se comportam de forma parecida |
| `region` | Região do local | Notebook 02, geral | Idem |

## 3. Histórico da própria série — "provavelmente inútil, mantido para o modelo testar"

**Origem principal:** Notebook 03, seção **8** ("Quem vendeu mais continua vendendo mais?") — mostrou correlação ano a ano ≈ 0 para uma mesma série produto × loja: quem vendeu muito num ano não tem mais chance de vender muito no ano seguinte que qualquer outra série. Isso não prova que o histórico individual é inútil dentro de um modelo (só que é inútil como régua simples), então as colunas ficam na tabela para o modelo confirmar ou refutar isso formalmente.

| Coluna | O que representa | Origem |
|---|---|---|
| `sum_12m` | Soma vendida pela própria série (produto × loja) nos 12 meses até o corte | Notebook 03, seção 8 |
| `sum_3m` | Soma vendida pela própria série nos 3 meses até o corte | Notebook 03, seção 8 |
| `avg_monthly_12m` | `sum_12m ÷ 12` — média móvel de 12 meses da própria série | Notebook 03 — é a "régua MM12" testada e superada pela régua final (seção 3 e 10) |
| `avg_monthly_3m` | `sum_3m ÷ 3` — média móvel de 3 meses da própria série | Notebook 03 — régua "MM3", a pior das réguas simples testadas (seção 3) |
| `months_with_sale_12m` | Em quantos dos 12 meses até o corte a série teve venda > 0 | Notebook 02, seção 3 ("Frequência de venda") — mesmos cortes usados aqui |
| `frequency_class` | `alta` (5+ meses), `media` (3-4), `baixa` (1-2), `sem_venda` (0) | Notebook 02, seção 3 — mesma classificação de frequência de venda |
| `months_since_last_sale` | Meses desde a última venda da série até o corte (0 = vendeu no próprio mês) | Notebook 02, seção 4 ("Fase de vida") |
| `is_stopped_12m` | `true` quando a série não vendeu nada nos 12 meses até o corte | Notebook 02, seção 4 — corresponde à `life_phase = 'parada'`, que no notebook 02 mostrou que 98% dessas séries voltam a vender no ano seguinte (não é descontinuação) |

## 4. Nível de grupo — features essenciais

**Origem principal:** Notebook 01, seção **B5** ("Quanto da variação a estação explica?") — mostrou que olhando uma série isolada a estação explica só ~3,8% da variação mês a mês, mas ao somar por categoria × loja isso sobe para ~60,5%. O sinal real mora no grupo, não na série. Notebook 03, seção **7** ("De onde vem o nível: da série, do produto ou da categoria?") confirmou isso numericamente: a média da categoria na loja prevê melhor do que a própria série ou o produto nas outras lojas.

| Coluna | O que representa | Origem |
|---|---|---|
| `categoria_local_avg_12m` | Média de `sum_12m` entre todos os produtos da mesma categoria, na mesma loja, naquele corte | Notebook 01 (B5) + Notebook 03 (seção 7) — feature isolada mais forte da tabela |
| `categoria_local_n_series` | Quantos produtos (séries) entraram nessa média | Contexto de confiabilidade: grupo pequeno = média mais ruidosa |
| `produto_locais_avg_12m` | Média de `sum_12m` do mesmo produto, somando os outros locais onde ele vende | Notebook 03, seções 7 e 8 — testado como alternativa à categoria × loja, teve desempenho equivalente (não melhor) |
| `produto_locais_n_locations` | Em quantos locais o produto já vendia naquele corte | Notebook 02, seção 7 ("Alcance dos produtos") — proxy de alcance; 92% dos produtos vendem nos 6 locais |

## 5. Sazonalidade e tendência — features essenciais

**Origem principal:** Notebook 03, seções **5** (erro por mês de corte / efeito de estação) e **6** (viés e tendência de crescimento).

| Coluna | O que representa | Origem |
|---|---|---|
| `seasonal_index_month_plus1` | Índice sazonal do 1º mês previsto, calculado só com histórico até o corte | Notebook 01 (B4/B6 — existência e força da sazonalidade) + `ml_seasonal_trend` |
| `seasonal_index_month_plus2` | Índice sazonal do 2º mês previsto | Idem |
| `seasonal_index_month_plus3` | Índice sazonal do 3º mês previsto | Idem |
| `season_sum_next_3m` | Soma dos três índices sazonais acima | Notebook 03, seção 5 — essencial, remove o viés de época |
| `trend_ready` | `false` nos cortes sem 24 meses de histórico (growth/trend ficam nulos) | Regra de engenharia derivada da necessidade de comparar 12m vs 12m anteriores |
| `growth_12m` | Crescimento da demanda: soma dos 12 meses até o corte ÷ soma dos 12 meses anteriores | Notebook 02, seção 6 ("Tendência") + Notebook 03, seção 2 |
| `trend_factor` | Fator de correção que remove o viés (~-9%) que o crescimento de ~15%/ano causa em qualquer média do passado | Notebook 03, seção 6 — essencial |

## 6. Baseline entregue como feature/prior

| Coluna | O que representa | Origem |
|---|---|---|
| `baseline_pred_categoria_local_idx_trend` | `categoria_local_avg_12m ÷ 12 × season_sum_next_3m × trend_factor` — a régua vencedora | Notebook 03, seção **14** ("A base de comparação") — WAPE de 86,6% por produto, 10,7% por categoria × loja, 6,1% por loja, viés de -2,8%. Entregue como feature porque o modelo só se justifica se **melhorar o resíduo dela**, não se reaprender a mesma conta do zero |

## 7. Alvo e controle de treino/inferência

| Coluna | O que representa | Origem |
|---|---|---|
| `target_3m` | Total real vendido pela série nos 3 meses seguintes ao corte — a variável a prever | Notebook 01, seção **B6** ("O que prever: um mês ou o total de 3 meses?") — decidiu prever a soma de 3 meses em vez do próximo mês isolado, pois reduz pela metade a proporção de metas zero e o ruído aleatório |
| `is_target_complete` | `true` = linha de treino/avaliação (target conhecido); `false` = linha de inferência (corte recente demais, os 3 meses seguintes ainda não aconteceram por inteiro) | Regra de engenharia — filtrar por essa flag para treinar/avaliar, e usar o corte mais recente sem ela para gerar a previsão real |

---

## Resumo — o que usar no modelo

- **Sempre incluir:** `categoria_local_avg_12m`, `season_sum_next_3m` (ou os 3 índices separados), `growth_12m`, `trend_factor`, `baseline_pred_categoria_local_idx_trend`.
- **Incluir para o modelo testar (expectativa baixa de ganho):** `sum_12m`, `sum_3m`, `months_since_last_sale`, `frequency_class`, `is_stopped_12m`, `produto_locais_avg_12m`, `produto_locais_n_locations`, `categoria_local_n_series`.
- **Baixa prioridade / categóricas de controle:** `category_name`, `location_name`, `location_type`, `region`, `brand_name`, `sale_price`.
- **Excluir do treino:** `sk_product`, `sk_location`, `sku`, `product_name`, `cutoff` (usar `cutoff` só para o split temporal).
- **Alvo:** `target_3m`, filtrando `is_target_complete = true` para treino/avaliação.
