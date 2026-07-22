-- stg_order_items.sql

with source as (

    select *
    from {{ source('bronze', 'order_items') }}

)

select
    cast(id as integer) as order_item_id
    , cast(order_id as integer) as order_id
    , cast(product_variant_id as integer) as product_variant_id
    , cast(round(quantity, 2) as decimal(10, 2)) as quantity_ordered
    , unit_price
    , icms_rate
    , ipi_rate
    , line_total as original_line_total

from source
