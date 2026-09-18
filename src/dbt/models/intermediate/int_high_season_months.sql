-- ============================================================
-- int_high_season_months.sql
-- Grão:
-- uma linha por mês do ano (1 a 12)
--
-- Define quais meses são alta temporada a partir da demanda
-- observada, em vez de uma lista fixa de meses. Um mês é alta
-- temporada quando a demanda média dele ao longo dos anos é maior
-- que a média geral dos 12 meses.
--
-- Demanda = quantity_ordered de pedidos confirmados ou pagos, a
-- mesma definição de agg_demand_daily (P2 do plano de ML). Vem de
-- int_orders/int_order_items, e não de fact_order_items, porque
-- dim_date usa esta tabela e fact_order_items depende de dim_date.
--
-- Só entram meses completos: o primeiro e o último mês com pedido
-- no dataset costumam estar pela metade e puxariam a média do seu
-- mês do ano para baixo.
--
-- A média geral é a média das 12 médias mensais, não a média de
-- todos os meses completos. Assim cada mês do ano pesa igual, mesmo
-- que alguns tenham um ano a mais de dados completos que outros —
-- sem isso, os meses com mais anos puxariam a média geral para o
-- nível deles.
--
-- A classificação acompanha os dados: meses perto da média geral
-- (seasonal_index perto de 1) podem mudar de lado quando o
-- histórico cresce.
-- ============================================================

with orders as (
    select
        order_id
        , placed_at
    from {{ ref('int_orders') }}
    where
        status in ('confirmed', 'paid')
        and placed_at is not null
)

, order_items as (
    select
        order_id
        , quantity_ordered
    from {{ ref('int_order_items') }}
)

, monthly_demand as (
    select
        cast(date_trunc('month', orders.placed_at) as date) as month_start_date
        , sum(order_items.quantity_ordered) as demand_quantity
    from order_items
    inner join orders
        on order_items.order_id = orders.order_id
    group by cast(date_trunc('month', orders.placed_at) as date)
)

, month_bounds as (
    select
        min(month_start_date) as first_month
        , max(month_start_date) as last_month
    from monthly_demand
)

, complete_months as (
    select monthly_demand.*
    from monthly_demand
    cross join month_bounds
    where
        monthly_demand.month_start_date > month_bounds.first_month
        and monthly_demand.month_start_date < month_bounds.last_month
)

, month_of_year as (
    select
        month(month_start_date) as month_number
        , count(*) as complete_months_count
        , avg(demand_quantity) as avg_monthly_demand
    from complete_months
    group by month(month_start_date)
)

, overall as (
    select avg(avg_monthly_demand) as overall_avg_monthly_demand
    from month_of_year
)

, final as (
    select
        month_of_year.month_number
        , month_of_year.complete_months_count
        , round(month_of_year.avg_monthly_demand, 2) as avg_monthly_demand
        , round(overall.overall_avg_monthly_demand, 2) as overall_avg_monthly_demand
        , round(
            month_of_year.avg_monthly_demand / overall.overall_avg_monthly_demand
            , 4
        ) as seasonal_index
        , month_of_year.avg_monthly_demand > overall.overall_avg_monthly_demand
            as is_high_season
    from month_of_year
    cross join overall
)

select * from final
