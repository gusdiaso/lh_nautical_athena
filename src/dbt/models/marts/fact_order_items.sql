-- ============================================================
-- fact_order_items.sql
-- Grão:
-- uma linha por item pertencente a um pedido de venda
--
-- A fato permite analisar faturamento, descontos, impostos,
-- rentabilidade comercial, canal de venda e cancelamentos
-- no nível de SKU.
--
-- O desconto do pedido é alocado proporcionalmente entre
-- seus itens com base no valor bruto de cada linha.
--
-- Os valores totais do cabeçalho do pedido não são mantidos
-- nesta fato, pois seriam repetidos para cada item e poderiam
-- causar dupla contagem nas ferramentas analíticas.
-- ============================================================

with order_items as (
    select
        order_item_id
        , order_id
        , product_variant_id
        , quantity_ordered
        , unit_price
        , icms_rate
        , ipi_rate
        , original_line_total
        , icms_amount
        , ipi_amount
        , total_tax_amount
        , total_with_taxes
    from {{ ref('int_order_items') }}
)

, orders as (
    select
        order_id
        , order_number
        , channel
        , customer_id
        , salesperson_id
        , location_id
        , status
        , discount_amount
        , placed_at
    from {{ ref('int_orders') }}
)

, order_line_totals as (
    select
        order_id
        , sum(original_line_total) as calculated_order_line_total
    from order_items
    group by order_id
)

, enriched_order_items as (
    select
        order_items.order_item_id
        , order_items.order_id
        , order_items.product_variant_id
        , orders.order_number
        , orders.channel
        , orders.customer_id
        , orders.location_id
        , orders.status as order_status
        , orders.placed_at
        , order_items.quantity_ordered
        , order_items.unit_price
        , order_items.icms_rate
        , order_items.ipi_rate
        , order_items.original_line_total
        , order_items.icms_amount
        , order_items.ipi_amount
        , order_items.total_tax_amount
        , order_items.total_with_taxes
        , case
            when orders.salesperson_id is not null
                then orders.salesperson_id
            when
                regexp_replace(
                    lower(coalesce(orders.channel, ''))
                    , '[^a-z0-9]'
                    , ''
                ) = 'ecommerce'
                then -2
            else -3
        end as resolved_employee_id
        , case
            when
                order_line_totals.calculated_order_line_total > 0
                and orders.discount_amount is not null
                then round(
                    orders.discount_amount
                    * (
                        order_items.original_line_total
                        / order_line_totals.calculated_order_line_total
                    )
                    , 2
                )
            else cast(0 as decimal(18, 2))
        end as allocated_discount_amount
    from order_items
    inner join orders
        on order_items.order_id = orders.order_id
    left join order_line_totals
        on order_items.order_id = order_line_totals.order_id
)

, products as (
    select
        sk_product
        , nk_product_variant_id
        , cost_price
        , gross_margin_amount
        , gross_margin_percentage
        , total_tax_rate
        , is_profitable
    from {{ ref('dim_products') }}
)

, customers as (
    select
        sk_customer
        , nk_customer_id
    from {{ ref('dim_customers') }}
)

, locations as (
    select
        sk_location
        , nk_location_id
    from {{ ref('dim_locations') }}
)

, employees as (
    select
        sk_employee
        , nk_employee_id
    from {{ ref('dim_employees') }}
)

, dates as (
    select
        sk_date
        , full_date
    from {{ ref('dim_date') }}
)

, joined as (
    select
        enriched_order_items.order_item_id as nk_order_item_id
        , enriched_order_items.order_id as nk_order_id
        , enriched_order_items.order_number
        , dates.sk_date
        , enriched_order_items.channel
        , enriched_order_items.order_status
        , enriched_order_items.quantity_ordered
        , enriched_order_items.unit_price
        , enriched_order_items.original_line_total as gross_line_total
        , enriched_order_items.allocated_discount_amount
        , enriched_order_items.icms_rate
        , enriched_order_items.ipi_rate
        , enriched_order_items.icms_amount
        , enriched_order_items.ipi_amount
        , enriched_order_items.total_tax_amount
        , enriched_order_items.total_with_taxes
        , products.cost_price as standard_unit_cost
        , products.gross_margin_amount
        , products.gross_margin_percentage
        , products.total_tax_rate
        , products.is_profitable
        , enriched_order_items.placed_at
        , cast(1 as integer) as order_item_count
        , {{ sk_from_keys(["'order_item'", 'enriched_order_items.order_item_id']) }} as sk_order_item
        , coalesce(
            products.sk_product
            , md5('product||nao_informado')
        ) as sk_product
        , coalesce(
            customers.sk_customer
            , md5('customer||nao_informado')
        ) as sk_customer
        , coalesce(
            locations.sk_location
            , md5('location||nao_informada')
        ) as sk_location
        , coalesce(
            employees.sk_employee
            , md5('employee||nao_informado')
        ) as sk_employee
        , round(
            enriched_order_items.original_line_total
            - enriched_order_items.allocated_discount_amount
            , 2
        ) as net_line_total
        , round(
            enriched_order_items.quantity_ordered
            * products.cost_price
            , 2
        ) as estimated_cost_of_goods_sold
        , round(
            (
                enriched_order_items.original_line_total
                - enriched_order_items.allocated_discount_amount
            )
            - (
                enriched_order_items.quantity_ordered
                * products.cost_price
            )
            , 2
        ) as estimated_gross_profit
        , enriched_order_items.order_status = 'cancelled' as is_cancelled
        , enriched_order_items.order_status = 'paid' as is_paid
        , enriched_order_items.order_status = 'confirmed' as is_confirmed
        , enriched_order_items.order_status = 'draft' as is_draft
    from enriched_order_items
    left join products
        on
            enriched_order_items.product_variant_id
            = products.nk_product_variant_id
    left join customers
        on
            enriched_order_items.customer_id
            = customers.nk_customer_id
    left join locations
        on
            enriched_order_items.location_id
            = locations.nk_location_id
    left join employees
        on
            enriched_order_items.resolved_employee_id
            = employees.nk_employee_id
    left join dates
        on
            cast(enriched_order_items.placed_at as date)
            = dates.full_date
)

, final as (
    select
        sk_order_item
        , nk_order_item_id
        , nk_order_id
        , order_number
        , sk_product
        , sk_customer
        , sk_location
        , sk_employee
        , sk_date
        , channel
        , order_status
        , quantity_ordered
        , unit_price
        , gross_line_total
        , allocated_discount_amount
        , net_line_total
        , icms_rate
        , ipi_rate
        , icms_amount
        , ipi_amount
        , total_tax_amount
        , total_with_taxes
        , standard_unit_cost
        , gross_margin_amount
        , gross_margin_percentage
        , total_tax_rate
        , is_profitable
        , estimated_cost_of_goods_sold
        , estimated_gross_profit
        , placed_at
        , is_cancelled
        , is_paid
        , is_confirmed
        , is_draft
        , order_item_count
    from joined
)

select * from final
