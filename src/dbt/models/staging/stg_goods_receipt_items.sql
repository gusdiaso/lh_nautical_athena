-- stg_goods_receipt_items.sql

with source as (

    select *
    from {{ source('bronze', 'goods_receipt_items') }}

)

select
    cast(id as integer) as goods_receipt_item_id
    , cast(goods_receipt_id as integer) as goods_receipt_id
    , cast(purchase_order_item_id as integer) as purchase_order_item_id
    , cast(round(quantity_received, 2) as decimal(10, 2)) as quantity_received

from source
