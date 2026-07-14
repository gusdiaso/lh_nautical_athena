with source as (

    select *
    from {{ ref('int_brands') }}

)

select
    md5(cast(brand_id as string)) as sk_brand,
    brand_id as nk_brand_id,
    name,
    country,
    is_active,
    created_at,
    updated_at

from source
where brand_id is not null