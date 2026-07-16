with source as (

    select *
    from {{ ref('stg_purchase_order_items') }}

)

, base as (

    select
        purchase_order_item_id
        , purchase_order_id
        , product_variant_id
        , quantity_ordered
        , unit_cost
        , line_total
    from source
    where purchase_order_item_id is not null

)

, deduplicated as (

    select
        *
        , row_number() over (
            partition by purchase_order_item_id
            order by purchase_order_item_id
        ) as record_rank
    from base

)

select
    purchase_order_item_id
    , purchase_order_id
    , product_variant_id
    , quantity_ordered
    , unit_cost
    , line_total

from deduplicated
where record_rank = 1