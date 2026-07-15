with source as (

    select *
    from {{ source('bronze', 'product_suppliers') }}

)

select
    -- Chave surrogate da relacao produto-fornecedor baseada na chave composta do negocio.
    product_variant_id
    , supplier_id
    , supplier_sku
    , last_quoted_cost
    , lead_time_days
    , is_preferred
    , created_at
    , updated_at
    , md5(
        concat_ws(
            '||'
            , cast(product_variant_id as string)
            , cast(supplier_id as string)
        )
    ) as sk_product_supplier

from source
