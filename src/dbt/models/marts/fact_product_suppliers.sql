with source as (

    select *
    from {{ ref('int_product_suppliers') }}

)

select
    cast(date_format(current_date(), 'yyyyMMdd') as string) as sk_date,
    sk_product_supplier,
    product_variant_id,
    supplier_id,
    supplier_sku,
    last_quoted_cost,
    lead_time_days,
    is_preferred

from source
where sk_product_supplier is not null