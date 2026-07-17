with source as (

    select *
    from {{ ref('int_brands') }}

)

select
    md5(cast(brand_id as string)) as sk_brand,
    brand_id,
    brand_name,
    country,
    is_active

from source
where brand_id is not null