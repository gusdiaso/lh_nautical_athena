with source as (

    select *
    from {{ ref('stg_goods_receipt_items') }}

)

, purchase_order_items as (

    select
        purchase_order_item_id
        , line_total
        , unit_cost
    from {{ ref('stg_purchase_order_items') }}

)

, base as (

    select
        gri.goods_receipt_item_id
        , gri.goods_receipt_id
        , gri.purchase_order_item_id
        , round(
            cast(poi.line_total as decimal(18, 4))
            / nullif(cast(poi.unit_cost as decimal(18, 4)), 0)
            , 2
        ) as quantity_received
    from source as gri
    inner join purchase_order_items as poi
        on gri.purchase_order_item_id = poi.purchase_order_item_id
    where gri.goods_receipt_item_id is not null

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
