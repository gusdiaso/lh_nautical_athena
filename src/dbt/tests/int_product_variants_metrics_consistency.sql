select
    product_variant_id,
    sale_price,
    cost_price,
    gross_margin_amount,
    gross_margin_percentage,
    total_tax_rate,
    is_profitable
from {{ ref('int_product_variants') }}
where
    round(sale_price - cost_price, 2) <> gross_margin_amount

    or (
        sale_price > 0
        and round(
            ((sale_price - cost_price) / sale_price) * 100,
            2
        ) <> gross_margin_percentage
    )

    or round(icms_rate + ipi_rate, 2) <> total_tax_rate

    or (
        sale_price > cost_price
        and is_profitable = false
    )

    or (
        sale_price <= cost_price
        and is_profitable = true
    )