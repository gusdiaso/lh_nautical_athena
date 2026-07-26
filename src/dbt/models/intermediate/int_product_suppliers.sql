with source as (

    select *
    from {{ ref('stg_product_suppliers') }}

)

, base as (

    select
        product_variant_id
        , supplier_id
        , last_quoted_cost
        , lead_time_days
        , is_preferred
        , md5(
            concat_ws(
                '||'
                , cast(product_variant_id as string)
                , cast(supplier_id as string)
            )
        ) as sk_product_supplier
        , case
            when supplier_sku is null
                or upper(trim(supplier_sku)) in ('TBD', '?', 'SEM-CODIGO', '')
            then concat(
                'SUP-',
                lpad(cast(supplier_id as string), 3, '0'),
                '-',
                lpad(cast(product_variant_id as string), 5, '0')
            )
            else trim(supplier_sku)
          end as supplier_sku
    from source
    where
        product_variant_id is not null
        and supplier_id is not null

)

, deduplicated as (

    select
        *
        , row_number() over (
            partition by sk_product_supplier
            order by last_quoted_cost desc nulls last
        ) as record_rank
    from base

)

select
    sk_product_supplier
    , product_variant_id
    , supplier_id
    , supplier_sku
    , last_quoted_cost
    , lead_time_days
    , is_preferred

from deduplicated
where record_rank = 1
