-- stg_purchase_order_items.sql

with source as (

    select *
    from {{ source('bronze', 'purchase_order_items') }}

)

select
    cast(id as integer) as purchase_order_item_id
    , purchase_order_id
    , product_variant_id
    , cast(round(quantity_ordered, 2) as decimal(10, 2)) as quantity_ordered
    , unit_cost
    , line_total

from source
