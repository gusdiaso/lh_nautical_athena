-- ============================================================
-- fact_purchase_order_items.sql
-- Grão:
-- uma linha por item pertencente a um pedido de compra
--
-- A fato preserva os valores na moeda original e também
-- apresenta a conversão para BRL usando a cotação associada
-- à data de emissão do pedido de compra.
--
-- Quando a cotação não estiver disponível, os valores em BRL
-- permanecem nulos para não criar falsos custos iguais a zero.
--
-- Os totais do cabeçalho do pedido não são mantidos nesta
-- fato, evitando repetição e dupla contagem entre os itens.
-- ============================================================

with purchase_order_items as (
    select
        purchase_order_item_id
        , purchase_order_id
        , product_variant_id
        , quantity_ordered
        , unit_cost
        , line_total
    from {{ ref('int_purchase_order_items') }}
)

, purchase_orders as (
    select
        purchase_order_id
        , po_number
        , supplier_id
        , buyer_id
        , destination_location_id
        , status
        , currency
        , exchange_rate_sell
        , placed_at
        , expected_delivery_at
    from {{ ref('int_purchase_orders') }}
)

, products as (
    select
        sk_product
        , nk_product_variant_id
    from {{ ref('dim_products') }}
)

, suppliers as (
    select
        sk_supplier
        , nk_supplier_id
    from {{ ref('dim_suppliers') }}
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
        md5(
            concat_ws(
                '||'
                , 'purchase_order_item'
                , cast(
                    purchase_order_items.purchase_order_item_id
                    as string
                )
            )
        ) as sk_purchase_order_item
        , purchase_order_items.purchase_order_item_id
            as nk_purchase_order_item_id
        , purchase_order_items.purchase_order_id
            as nk_purchase_order_id
        , purchase_orders.po_number
        , coalesce(
            products.sk_product
            , md5('product||nao_informado')
        ) as sk_product
        , coalesce(
            suppliers.sk_supplier
            , md5('supplier||nao_informado')
        ) as sk_supplier
        , coalesce(
            locations.sk_location
            , md5('location||nao_informada')
        ) as sk_location
        , coalesce(
            employees.sk_employee
            , md5('employee||nao_informado')
        ) as sk_employee
        , order_dates.sk_date as sk_order_date
        , expected_dates.sk_date as sk_expected_delivery_date
        , purchase_orders.status as purchase_order_status
        , purchase_orders.currency
        , purchase_orders.exchange_rate_sell
        , purchase_order_items.quantity_ordered
        , purchase_order_items.unit_cost
            as unit_cost_original_currency
        , purchase_order_items.line_total
            as line_total_original_currency
        , case
            when purchase_orders.currency = 'BRL'
                then purchase_order_items.unit_cost
            when purchase_orders.exchange_rate_sell is not null
                then round(
                    purchase_order_items.unit_cost
                    * purchase_orders.exchange_rate_sell
                    , 2
                )
        end as unit_cost_brl
        , case
            when purchase_orders.currency = 'BRL'
                then purchase_order_items.line_total
            when purchase_orders.exchange_rate_sell is not null
                then round(
                    purchase_order_items.line_total
                    * purchase_orders.exchange_rate_sell
                    , 2
                )
        end as line_total_brl
        , purchase_orders.placed_at
        , purchase_orders.expected_delivery_at
        , purchase_orders.expected_delivery_at
            < current_date() as is_expected_delivery_overdue
        , cast(1 as integer) as purchase_order_item_count
    from purchase_order_items
    inner join purchase_orders
        on purchase_order_items.purchase_order_id
            = purchase_orders.purchase_order_id
    left join products
        on purchase_order_items.product_variant_id
            = products.nk_product_variant_id
    left join suppliers
        on purchase_orders.supplier_id
            = suppliers.nk_supplier_id
    left join locations
        on purchase_orders.destination_location_id
            = locations.nk_location_id
    left join employees
        on coalesce(purchase_orders.buyer_id, -3)
            = employees.nk_employee_id
    left join dates as order_dates
        on cast(purchase_orders.placed_at as date)
            = order_dates.full_date
    left join dates as expected_dates
        on purchase_orders.expected_delivery_at
            = expected_dates.full_date
)

, final as (
    select
        sk_purchase_order_item
        , nk_purchase_order_item_id
        , nk_purchase_order_id
        , po_number
        , sk_product
        , sk_supplier
        , sk_location
        , sk_employee
        , sk_order_date
        , sk_expected_delivery_date
        , purchase_order_status
        , currency
        , exchange_rate_sell
        , quantity_ordered
        , unit_cost_original_currency
        , line_total_original_currency
        , unit_cost_brl
        , line_total_brl
        , placed_at
        , expected_delivery_at
        , is_expected_delivery_overdue
        , purchase_order_item_count
    from joined
)

select * from final;