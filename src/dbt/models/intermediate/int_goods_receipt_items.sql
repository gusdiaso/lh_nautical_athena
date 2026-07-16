with source as (

    select *
    from {{ ref('stg_goods_receipt_items') }}

)

, base as (

    select
        goods_receipt_item_id
        , goods_receipt_id
        , purchase_order_item_id
        , quantity_received
    from source
    where goods_receipt_item_id is not null

)

, deduplicated as (

    select
        *
        , row_number() over (
            partition by goods_receipt_item_id
            order by goods_receipt_item_id
        ) as record_rank
    from base

)

select
    goods_receipt_item_id
    , goods_receipt_id
    , purchase_order_item_id
    , quantity_received

from deduplicated
where record_rank = 1