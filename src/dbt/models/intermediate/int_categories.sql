with source as (

    select *
    from {{ ref('stg_categories') }}

),

base as (

    select
        category_id,
        trim(name) as name,
        lower(trim(slug)) as slug,
        parent_category_id,
        is_active,
        created_at,
        updated_at
    from source
    where category_id is not null

),

deduplicated as (

    select
        *,
        row_number() over (
            partition by category_id
            order by updated_at desc nulls last, created_at desc nulls last
        ) as record_rank
    from base

)

select
    category_id,
    name,
    slug,
    parent_category_id,
    is_active,
    created_at,
    updated_at

from deduplicated
where record_rank = 1