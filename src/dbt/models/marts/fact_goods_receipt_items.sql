-- ============================================================
-- fact_goods_receipt_items.sql
-- Grão:
-- uma linha por item registrado em um recebimento de mercadoria
--
-- A fato conecta o recebimento físico ao pedido de compra,
-- permitindo medir quantidade recebida, saldo pendente e
-- cumprimento do prazo previsto pelo fornecedor.
--
-- O saldo após o recebimento é calculado de forma acumulada
-- para suportar entregas parciais do mesmo item.
--
-- A quantidade total recebida não é repetida nas linhas.
-- A posição após cada evento é representada por
-- cumulative_quantity_received.
-- ============================================================

with goods_receipt_items as (
    select
        goods_receipt_item_id
        , goods_receipt_id
        , purchase_order_item_id
        , quantity_received
    from {{ ref('int_goods_receipt_items') }}
)

, goods_receipts as (
    select
        goods_receipt_id
        , purchase_order_id
        , received_by_employee_id
        , received_at
    from {{ ref('int_goods_receipts') }}
)

, purchase_order_items as (
    select
        purchase_order_item_id
        , purchase_order_id
        , product_variant_id
        , quantity_ordered
        , unit_cost
    from {{ ref('int_purchase_order_items') }}
)

, purchase_orders as (
    select
        purchase_order_id
        , po_number
        , supplier_id
        , destination_location_id
        , status
        , currency
        , exchange_rate_sell
        , placed_at
        , expected_delivery_at
    from {{ ref('int_purchase_orders') }}
)

, receipt_base as (
    select
        goods_receipt_items.goods_receipt_item_id
        , goods_receipt_items.goods_receipt_id
        , goods_receipt_items.purchase_order_item_id
        , goods_receipts.purchase_order_id
        , purchase_order_items.product_variant_id
        , purchase_orders.po_number
        , purchase_orders.supplier_id
        , purchase_orders.destination_location_id
        , goods_receipts.received_by_employee_id
        , purchase_orders.status as purchase_order_status
        , purchase_orders.currency
        , purchase_orders.exchange_rate_sell
        , purchase_order_items.quantity_ordered
        , goods_receipt_items.quantity_received
        , purchase_order_items.unit_cost
        , purchase_orders.placed_at
        , purchase_orders.expected_delivery_at
        , goods_receipts.received_at
        , sum(goods_receipt_items.quantity_received) over (
            partition by goods_receipt_items.purchase_order_item_id
            order by
                goods_receipts.received_at
                , goods_receipt_items.goods_receipt_item_id
            rows between unbounded preceding and current row
        ) as cumulative_quantity_received
    from goods_receipt_items
    inner join goods_receipts
        on
            goods_receipt_items.goods_receipt_id
            = goods_receipts.goods_receipt_id
    inner join purchase_order_items
        on
            goods_receipt_items.purchase_order_item_id
            = purchase_order_items.purchase_order_item_id
    inner join purchase_orders
        on
            purchase_order_items.purchase_order_id
            = purchase_orders.purchase_order_id
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
        receipt_base.goods_receipt_item_id
            as nk_goods_receipt_item_id
        , receipt_base.goods_receipt_id
            as nk_goods_receipt_id
        , receipt_base.purchase_order_item_id
            as nk_purchase_order_item_id
        , receipt_base.purchase_order_id
            as nk_purchase_order_id
        , receipt_base.po_number
        , receipt_dates.sk_date as sk_receipt_date
        , order_dates.sk_date as sk_order_date
        , expected_dates.sk_date as sk_expected_delivery_date
        , receipt_base.purchase_order_status
        , receipt_base.currency
        , receipt_base.exchange_rate_sell
        , receipt_base.quantity_ordered
        , receipt_base.quantity_received
        , receipt_base.cumulative_quantity_received
        , receipt_base.unit_cost
            as unit_cost_original_currency
        , receipt_base.placed_at
        , receipt_base.expected_delivery_at
        , receipt_base.received_at
        , cast(1 as integer) as goods_receipt_item_count
        , {{ sk_from_keys(["'goods_receipt_item'", 'receipt_base.goods_receipt_item_id']) }} as sk_goods_receipt_item
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
        , greatest(
            receipt_base.quantity_ordered
            - receipt_base.cumulative_quantity_received
            , 0
        ) as remaining_quantity_after_receipt
        , receipt_base.cumulative_quantity_received
        >= receipt_base.quantity_ordered as is_fully_received
        , receipt_base.cumulative_quantity_received
        < receipt_base.quantity_ordered as is_partial_receipt
        , round(
            receipt_base.quantity_received
            * receipt_base.unit_cost
            , 2
        ) as received_value_original_currency
        , case
            when receipt_base.currency = 'BRL'
                then round(
                    receipt_base.quantity_received
                    * receipt_base.unit_cost
                    , 2
                )
            when receipt_base.exchange_rate_sell is not null
                then round(
                    receipt_base.quantity_received
                    * receipt_base.unit_cost
                    * receipt_base.exchange_rate_sell
                    , 2
                )
        end as received_value_brl
        , datediff(
            cast(receipt_base.received_at as date)
            , receipt_base.expected_delivery_at
        ) as delivery_variance_days
        , cast(receipt_base.received_at as date)
        > receipt_base.expected_delivery_at as is_late_receipt
    from receipt_base
    left join products
        on
            receipt_base.product_variant_id
            = products.nk_product_variant_id
    left join suppliers
        on
            receipt_base.supplier_id
            = suppliers.nk_supplier_id
    left join locations
        on
            receipt_base.destination_location_id
            = locations.nk_location_id
    left join employees
        on
            coalesce(receipt_base.received_by_employee_id, -3)
            = employees.nk_employee_id
    left join dates as receipt_dates
        on
            cast(receipt_base.received_at as date)
            = receipt_dates.full_date
    left join dates as order_dates
        on
            cast(receipt_base.placed_at as date)
            = order_dates.full_date
    left join dates as expected_dates
        on
            receipt_base.expected_delivery_at
            = expected_dates.full_date
)

, final as (
    select
        sk_goods_receipt_item
        , nk_goods_receipt_item_id
        , nk_goods_receipt_id
        , nk_purchase_order_item_id
        , nk_purchase_order_id
        , po_number
        , sk_product
        , sk_supplier
        , sk_location
        , sk_employee
        , sk_receipt_date
        , sk_order_date
        , sk_expected_delivery_date
        , purchase_order_status
        , currency
        , exchange_rate_sell
        , quantity_ordered
        , quantity_received
        , cumulative_quantity_received
        , remaining_quantity_after_receipt
        , is_fully_received
        , is_partial_receipt
        , unit_cost_original_currency
        , received_value_original_currency
        , received_value_brl
        , placed_at
        , expected_delivery_at
        , received_at
        , delivery_variance_days
        , is_late_receipt
        , goods_receipt_item_count
    from joined
)

select * from final
