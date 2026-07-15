-- stg_stock_levels.sql

with source as (

    select *
    from {{ source('bronze', 'stock_levels') }}

)

select
    product_variant_id
    , location_id
    , quantity_on_hand
    , reorder_point

from source
