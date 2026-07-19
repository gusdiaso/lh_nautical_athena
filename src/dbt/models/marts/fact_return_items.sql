-- ============================================================
-- fact_return_items.sql
-- Grão:
-- uma linha por item pertencente a uma devolução
--
-- A fato relaciona o item devolvido ao produto original,
-- produto de troca, cliente, localização e data da devolução.
--
-- O produto de troca permanece nulo quando a ação é refund,
-- pois nesse cenário a ausência não representa dado faltante,
-- mas uma relação que não se aplica.
--
-- O indicador de existência de reembolso pertence ao
-- cabeçalho da devolução e, por isso, recebe um nome que
-- explicita seu escopo.
-- ============================================================

with return_items as (
    select
        return_item_id
        , return_id
        , order_item_id
        , quantity_returned
        , action
        , exchange_variant_id
        , unit_refund_amount
        , is_exchange
        , is_refund
        , total_line_refund_amount
    from {{ ref('int_return_items') }}
)

, returns as (
    select
        return_id
        , return_number
        , order_id
        , customer_id
        , received_at_location_id
        , status
        , original_reason
        , reason_normalized
        , return_reason_group
        , has_refund_amount
        , created_at
    from {{ ref('int_returns') }}
)

, order_items as (
    select
        order_item_id
        , product_variant_id
    from {{ ref('int_order_items') }}
)

, products as (
    select
        sk_product
        , nk_product_variant_id
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
                , 'return_item'
                , cast(return_items.return_item_id as string)
            )
        ) as sk_return_item
        , return_items.return_item_id as nk_return_item_id
        , return_items.return_id as nk_return_id
        , return_items.order_item_id as nk_order_item_id
        , returns.order_id as nk_order_id
        , coalesce(
            returned_products.sk_product
            , md5('product||nao_informado')
        ) as sk_returned_product
        , case
            when return_items.is_exchange
                then coalesce(
                    exchange_products.sk_product
                    , md5('product||nao_informado')
                )
        end as sk_exchange_product
        , coalesce(
            customers.sk_customer
            , md5('customer||nao_informado')
        ) as sk_customer
        , coalesce(
            locations.sk_location
            , md5('location||nao_informada')
        ) as sk_location
        , dates.sk_date
        , returns.return_number
        , returns.status as return_status
        , returns.original_reason
        , returns.reason_normalized
        , returns.return_reason_group
        , return_items.action
        , return_items.quantity_returned
        , return_items.unit_refund_amount
        , return_items.total_line_refund_amount
        , return_items.is_exchange
        , return_items.is_refund
        , returns.has_refund_amount as return_has_refund_amount
        , returns.created_at as returned_at
        , cast(1 as integer) as returned_item_count
    from return_items
    inner join returns
        on return_items.return_id = returns.return_id
    left join order_items
        on return_items.order_item_id = order_items.order_item_id
    left join products as returned_products
        on order_items.product_variant_id
            = returned_products.nk_product_variant_id
    left join products as exchange_products
        on return_items.exchange_variant_id
            = exchange_products.nk_product_variant_id
    left join customers
        on returns.customer_id = customers.nk_customer_id
    left join locations
        on returns.received_at_location_id = locations.nk_location_id
    left join dates
        on cast(returns.created_at as date) = dates.full_date
)

, final as (
    select
        sk_return_item
        , nk_return_item_id
        , nk_return_id
        , nk_order_item_id
        , nk_order_id
        , sk_returned_product
        , sk_exchange_product
        , sk_customer
        , sk_location
        , sk_date
        , return_number
        , return_status
        , original_reason
        , reason_normalized
        , return_reason_group
        , action
        , quantity_returned
        , unit_refund_amount
        , total_line_refund_amount
        , is_exchange
        , is_refund
        , return_has_refund_amount
        , returned_at
        , returned_item_count
    from joined
)

select * from final;
