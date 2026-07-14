-- stg_purchase_order_items.sql

with source as (

    select *
    from {{ source('bronze', 'purchase_order_items') }}

)

select
    id as purchase_order_item_id
    , purchase_order_id
    , product_variant_id
    , quantity_ordered
    , unit_cost
    , line_total

from source
