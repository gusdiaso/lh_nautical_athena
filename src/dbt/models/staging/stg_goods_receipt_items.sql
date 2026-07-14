-- stg_goods_receipt_items.sql

with source as (

    select *
    from {{ source('bronze', 'goods_receipt_items') }}

)

select
    id as goods_receipt_item_id
    , goods_receipt_id
    , purchase_order_item_id
    , quantity_received

from source
