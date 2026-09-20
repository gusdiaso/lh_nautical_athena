-- ============================================================
-- ml_cutoff_panel.sql
-- Grão:
-- uma linha por produto (SKU) × loja × mês de corte (mês completo)
--
-- Porta para SQL o build_cutoff_panel de
-- src/analytics_ai/demand_moving_average.py: para cada corte, soma os
-- 12 e os 3 meses anteriores da própria série (sum_12m, sum_3m),
-- conta os meses com venda no último ano, mede há quantos meses
-- não vende e soma o alvo (target_3m = total dos 3 meses seguintes
-- ao corte). Roda para TODO corte possível do histórico, não só os
-- 12 de teste + 24 de calibração usados na avaliação do notebook
-- 04 — é a base de treino/inferência para o modelo de ML.
--
-- has_full_history_12m confirma que a janela de 12 meses anteriores
-- não tem buracos (mesmo teste de window_ok do notebook 04); só
-- essas linhas seguem para a tabela final — sem 12 meses cheios,
-- sum_12m e months_with_sale_12m não são comparáveis entre séries.
--
-- target_3m fica nulo quando a janela dos 3 meses seguintes está
-- incompleta (cortes recentes, cujo alvo ainda não aconteceu por
-- inteiro): essas linhas são de inferência (previsão de verdade),
-- não de treino.
-- ============================================================

with monthly as (
    select
        sk_product
        , sk_location
        , month_start_date
        , demand_quantity
    from {{ ref('ml_complete_monthly_demand') }}
)

, windows as (
    select
        sk_product
        , sk_location
        , month_start_date as cutoff
        , sum(demand_quantity) over (
            partition by sk_product, sk_location
            order by month_start_date
            rows between 11 preceding and current row
        ) as sum_12m
        , count(*) over (
            partition by sk_product, sk_location
            order by month_start_date
            rows between 11 preceding and current row
        ) as months_counted_12m
        , min(month_start_date) over (
            partition by sk_product, sk_location
            order by month_start_date
            rows between 11 preceding and current row
        ) as window_start_12m
        , sum(demand_quantity) over (
            partition by sk_product, sk_location
            order by month_start_date
            rows between 2 preceding and current row
        ) as sum_3m
        , sum(case when demand_quantity > 0 then 1 else 0 end) over (
            partition by sk_product, sk_location
            order by month_start_date
            rows between 11 preceding and current row
        ) as months_with_sale_12m
        , max(case when demand_quantity > 0 then month_start_date end) over (
            partition by sk_product, sk_location
            order by month_start_date
            rows between unbounded preceding and current row
        ) as last_sale_month
        , sum(demand_quantity) over (
            partition by sk_product, sk_location
            order by month_start_date
            rows between 1 following and 3 following
        ) as target_3m_raw
        , count(*) over (
            partition by sk_product, sk_location
            order by month_start_date
            rows between 1 following and 3 following
        ) as months_counted_future
        , max(month_start_date) over (
            partition by sk_product, sk_location
            order by month_start_date
            rows between 1 following and 3 following
        ) as window_end_future
    from monthly
)

, final as (
    select
        sk_product
        , sk_location
        , cutoff
        , sum_12m
        , sum_3m
        , months_with_sale_12m
        , cast(months_between(cutoff, last_sale_month) as int) as months_since_last_sale
        , months_counted_12m = 12
        and window_start_12m = add_months(cutoff, -11) as has_full_history_12m
        , months_counted_future = 3
        and window_end_future = add_months(cutoff, 3) as has_full_target_3m
        , case
            when months_counted_future = 3 and window_end_future = add_months(cutoff, 3)
                then target_3m_raw
        end as target_3m
    from windows
)

select * from final
where has_full_history_12m
