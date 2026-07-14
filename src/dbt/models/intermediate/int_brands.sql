with source as (

    select *
    from {{ ref('stg_brands') }}

),

base as (

    select
        brand_id,
        trim(name) as name,
        upper(trim(country)) as country,
        is_active,
        created_at,
        updated_at
    from source
    where brand_id is not null

),

deduplicated as (

    select
        *,
        row_number() over (
            partition by brand_id
            order by updated_at desc nulls last, created_at desc nulls last
        ) as record_rank
    from base

)

select
    brand_id,
    name,
    country,
    is_active,
    created_at,
    updated_at

from deduplicated
where record_rank = 1