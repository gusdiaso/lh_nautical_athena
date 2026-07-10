-- stg_product_variants.sql

with source as (

    select *
    from {{ source('bronze', 'product_variants') }}

)

select
    id as product_variant_id,
    product_id,
    sku,
    barcode_ean,
    sale_price,
    cost_price,
    weight_kg,
    icms_rate,
    ipi_rate,
    is_active,
    created_at,
    updated_at

from source