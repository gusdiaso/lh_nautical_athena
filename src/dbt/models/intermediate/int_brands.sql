with source as (

    select *
    from {{ ref('stg_brands') }}

),

base as (

    select
        brand_id,
        trim(name) as name,
        upper(trim(country)) as country,
        is_active
    from source
    where brand_id is not null

),

deduplicated as (

    select
        *,
        row_number() over (
            partition by brand_id
            order by brand_id
        ) as record_rank
    from base

)

select
    brand_id,
    name,
    country,
    is_active

from deduplicated
where record_rank = 1