-- ============================================================
-- ml_features_produto_loja_mes.sql
-- Grão:
-- uma linha por produto (SKU) × loja × mês de corte
--
-- Tabela final de features de Machine Learning (Etapa 3 do plano
-- de previsão) — alimenta os modelos da Etapa 4. Junta o painel de
-- corte (ml_cutoff_panel), a estação/tendência ponto-no-tempo
-- (ml_seasonal_trend) e os atributos de produto/loja, e calcula
-- os níveis de grupo que os notebooks 01-03 (notebooks/ml)
-- comprovaram serem o sinal mais forte.
--
-- O que cada bloco de colunas representa, e o veredito dos
-- notebooks 01-03 sobre ele (conclusão do notebook 03):
--
-- - Nível do grupo (categoria_local_avg_12m, produto_locais_avg_12m)
--   — ESSENCIAL: prevê melhor que a própria série (notebook 03,
--   seção 7), porque a venda de um produto isolado é quase acaso
--   (seção 8 — correlação ano a ano ≈ 0) e a categoria numa loja
--   concentra o sinal real de estação (notebook 01, seção B5: R²
--   sazonal de 3,8% por série contra 60,5% por categoria × loja).
-- - Estação e tendência (seasonal_index_month_plus1..3,
--   season_sum_next_3m, growth_12m, trend_factor) — ESSENCIAL:
--   removem o viés de época (notebook 03, seção 5) e de crescimento,
--   +15%/ano (seção 6). Recalculados por corte, sem usar o futuro
--   (ml_seasonal_trend).
-- - Histórico da própria série (sum_12m, sum_3m,
--   months_with_sale_12m, months_since_last_sale, frequency_class)
--   — PROVAVELMENTE INÚTIL, mantido para o modelo testar e
--   confirmar (notebook 03, seção 8).
-- - Atributos (category_name, brand_name, location_name,
--   location_type, region, sale_price) — BAIXA PRIORIDADE: todas as
--   categorias e locais vendem de forma parecida (notebook 02).
-- - baseline_pred_categoria_local_idx_trend — a régua vencedora do
--   notebook 03 (seção 14: WAPE 86,6% por produto, 10,7% por
--   categoria × local, 6,1% por local, viés −2,8%), entregue como
--   feature/prior: o modelo só se justifica se aprender a corrigir
--   o resíduo dela, não se reaprender a mesma conta do zero.
--
-- is_target_complete = false ⇒ linha de inferência (o alvo dos 3
-- meses seguintes ainda não aconteceu por inteiro); target_3m nulo
-- nesses casos. Filtrar por is_target_complete para treinar/avaliar
-- e pelo corte mais recente (sem is_target_complete) para prever.
-- ============================================================

with panel as (
    select
        sk_product
        , sk_location
        , cutoff
        , sum_12m
        , sum_3m
        , months_with_sale_12m
        , months_since_last_sale
        , target_3m
        , has_full_target_3m
    from {{ ref('ml_cutoff_panel') }}
)

, products as (
    select
        sk_product
        , sku
        , product_name
        , category_name
        , brand_name
        , sale_price
    from {{ ref('dim_products') }}
)

, locations as (
    select
        sk_location
        , location_name
        , location_type
        , region
    from {{ ref('dim_locations') }}
)

, seasonal_trend as (
    select
        cutoff
        , seasonal_index_month_plus1
        , seasonal_index_month_plus2
        , seasonal_index_month_plus3
        , season_sum_next_3m
        , trend_ready
        , growth_12m
        , trend_factor
    from {{ ref('ml_seasonal_trend') }}
)

, enriched as (
    select
        panel.*
        , products.sku
        , products.product_name
        , products.category_name
        , products.brand_name
        , products.sale_price
        , locations.location_name
        , locations.location_type
        , locations.region
        , seasonal_trend.seasonal_index_month_plus1
        , seasonal_trend.seasonal_index_month_plus2
        , seasonal_trend.seasonal_index_month_plus3
        , seasonal_trend.season_sum_next_3m
        , seasonal_trend.trend_ready
        , seasonal_trend.growth_12m
        , seasonal_trend.trend_factor
    from panel
    inner join products
        on panel.sk_product = products.sk_product
    inner join locations
        on panel.sk_location = locations.sk_location
    inner join seasonal_trend
        on panel.cutoff = seasonal_trend.cutoff
)

, grouped as (
    select
        enriched.*
        , avg(enriched.sum_12m) over (
            partition by enriched.category_name, enriched.sk_location, enriched.cutoff
        ) as categoria_local_avg_12m
        , count(*) over (
            partition by enriched.category_name, enriched.sk_location, enriched.cutoff
        ) as categoria_local_n_series
        , avg(enriched.sum_12m) over (
            partition by enriched.sk_product, enriched.cutoff
        ) as produto_locais_avg_12m
        , count(*) over (
            partition by enriched.sk_product, enriched.cutoff
        ) as produto_locais_n_locations
    from enriched
)

, final as (
    select
        grouped.cutoff
        , grouped.sk_product
        , grouped.sku
        , grouped.product_name
        , grouped.category_name
        , grouped.brand_name
        , grouped.sale_price
        , grouped.sk_location
        , grouped.location_name
        , grouped.location_type
        , grouped.region

        -- histórico da própria série — provavelmente inútil, testar (notebook 03, seção 8)
        , grouped.sum_12m
        , grouped.sum_3m
        , grouped.months_with_sale_12m
        , grouped.months_since_last_sale
        , grouped.categoria_local_n_series
        , grouped.produto_locais_n_locations
        , grouped.seasonal_index_month_plus1
        , grouped.seasonal_index_month_plus2

        -- nível do grupo — essencial (notebook 03, seção 7)
        , grouped.seasonal_index_month_plus3
        , grouped.season_sum_next_3m
        , grouped.trend_ready
        , grouped.growth_12m

        -- estação e tendência — essencial (notebook 03, seções 2, 5 e 6)
        , grouped.trend_factor
        , grouped.target_3m
        , grouped.has_full_target_3m as is_target_complete
        , round(grouped.sum_12m / 12.0, 4) as avg_monthly_12m
        , round(grouped.sum_3m / 3.0, 4) as avg_monthly_3m
        , case
            when grouped.months_with_sale_12m >= 5 then 'alta'
            when grouped.months_with_sale_12m >= 3 then 'media'
            when grouped.months_with_sale_12m >= 1 then 'baixa'
            else 'sem_venda'
        end as frequency_class
        , grouped.months_with_sale_12m = 0 as is_stopped_12m

        -- régua vencedora do notebook 03 (seção 14), entregue como feature/prior
        , round(grouped.categoria_local_avg_12m, 4) as categoria_local_avg_12m

        -- alvo e flag de treino × inferência
        , round(grouped.produto_locais_avg_12m, 4) as produto_locais_avg_12m
        , round(
            grouped.categoria_local_avg_12m / 12.0 * grouped.season_sum_next_3m * grouped.trend_factor
            , 4
        ) as baseline_pred_categoria_local_idx_trend
    from grouped
)

select * from final
