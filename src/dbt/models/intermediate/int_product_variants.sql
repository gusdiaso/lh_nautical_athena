with product_variants as (

    select *
    from {{ ref('stg_product_variants') }}

)

select
    product_variant_id,
    product_id,
    sku,
    barcode_ean,
    sale_price,
    cost_price,
    weight_kg,
    icms_rate,
    ipi_rate,
    is_active,

    round(
        sale_price - cost_price,
        2
    ) as gross_margin_amount,

    case
        when sale_price > 0 then
            round(
                ((sale_price - cost_price) / sale_price) * 100,
                2
            )
        else null
    end as gross_margin_percentage,

    round(
        icms_rate + ipi_rate,
        2
    ) as total_tax_rate,

    case
        when sale_price > cost_price then true
        else false
    end as is_profitable,

    created_at,
    updated_at

from product_variants