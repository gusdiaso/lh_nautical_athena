-- stg_products.sql

with source as (

    select *
    from {{ source('bronze', 'products') }}

)

select
    id as product_id
    , product_name
    , description
    , brand_id
    , category_id
    , ncm_code
    , unit_of_measure
    , is_active
    , created_at
    , updated_at

from source
