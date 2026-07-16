-- stg_products.sql

with source as (

    select *
    from {{ source('bronze', 'products') }}

)

select
    cast(id as integer) as product_id
    , name as product_name
    , description
    , cast(brand_id as integer) as brand_id
    , cast(category_id as integer) as category_id
    , ncm_code
    , unit_of_measure
    , is_active

from source
