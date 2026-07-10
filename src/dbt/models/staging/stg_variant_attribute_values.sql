-- stg_variant_attribute_values.sql

with source as (

    select *
    from {{ source('bronze', 'variant_attribute_values') }}

)

select
    product_variant_id,
    attribute_id,
    trim(value) as value

from source