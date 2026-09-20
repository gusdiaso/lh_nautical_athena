-- ============================================================
-- agg_sales_by_customer_state_month.sql
-- Grão:
-- mês (primeiro dia) × UF do cliente × localização de origem
-- × canal de venda
--
-- Base da análise de expansão da rede: volume e receita por UF de
-- destino e a origem que atendeu, para medir a distância real de
-- atendimento em pandas. O canal fica no grão porque venda de
-- balcão e e-commerce têm geografias diferentes: na loja física o
-- cliente foi até a unidade, no e-commerce pode estar em qualquer
-- UF.
--
-- Pedidos cancelados e rascunhos ficam de fora: nunca foram
-- atendidos. Cliente sem UF cadastrada cai em 'SEM_UF': sai do
-- ranking, mas continua na tabela para o volume total não ser
-- subestimado e a cobertura poder ser reportada.
-- ============================================================

with order_items as (
    select
        sk_customer
        , sk_location
        , sk_date
        , channel
        , quantity_ordered
        , net_line_total
        , estimated_gross_profit
    from {{ ref('fact_order_items') }}
    where
        not is_cancelled
        and not is_draft
)

, dates as (
    select
        sk_date
        , full_date
    from {{ ref('dim_date') }}
)

, customers as (
    select
        sk_customer
        , state
    from {{ ref('dim_customers') }}
)

, enriched as (
    select
        order_items.sk_location
        , order_items.channel
        , order_items.quantity_ordered
        , order_items.net_line_total
        , order_items.estimated_gross_profit
        , cast(date_trunc('month', dates.full_date) as date) as month_start_date
        , coalesce(upper(trim(customers.state)), 'SEM_UF') as customer_state
    from order_items
    inner join dates
        on order_items.sk_date = dates.sk_date
    left join customers
        on order_items.sk_customer = customers.sk_customer
)

, final as (
    select
        month_start_date
        , customer_state
        , sk_location
        , channel
        , sum(quantity_ordered) as quantity_ordered
        , sum(net_line_total) as net_revenue
        , sum(estimated_gross_profit) as estimated_gross_profit
        , count(*) as order_item_count
    from enriched
    group by
        month_start_date
        , customer_state
        , sk_location
        , channel
)

select * from final
