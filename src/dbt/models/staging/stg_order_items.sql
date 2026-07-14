-- stg_order_items.sql

with source as (

    select *
    from {{ source('bronze', 'order_items') }}

)

select
    id as order_item_id
    , order_id
    , product_variant_id
    , quantity
    , unit_price
    , icms_rate
    , ipi_rate
    , line_total

from source
