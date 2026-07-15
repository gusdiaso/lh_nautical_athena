with source as (

    select *
    from {{ ref('stg_product_suppliers') }}

),

base as (

    select
        md5(concat_ws('||', cast(product_variant_id as string), cast(supplier_id as string))) as sk_product_supplier,
        product_variant_id,
        supplier_id,
        trim(supplier_sku) as supplier_sku,
        last_quoted_cost,
        lead_time_days,
        is_preferred
    from source
    where product_variant_id is not null
      and supplier_id is not null

),

deduplicated as (

    select
        *,
        row_number() over (
            partition by sk_product_supplier
            order by sk_product_supplier
        ) as record_rank
    from base

)

select
    sk_product_supplier,
    product_variant_id,
    supplier_id,
    supplier_sku,
    last_quoted_cost,
    lead_time_days,
    is_preferred

from deduplicated
where record_rank = 1