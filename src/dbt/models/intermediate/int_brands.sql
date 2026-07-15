with source as (

    select *
    from {{ ref('stg_brands') }}

)

, base as (

    select
        brand_id
        , is_active
        , trim(brand_name) as brand_name
        , upper(trim(country)) as country
    from source
    where brand_id is not null

)

, deduplicated as (

    select
        *
        , row_number() over (
            partition by brand_id
            order by brand_id
        ) as record_rank
    from base

)

select
    brand_id
    , brand_name
    , country
    , is_active

from deduplicated
where record_rank = 1
