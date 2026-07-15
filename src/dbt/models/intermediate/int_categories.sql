with source as (

    select *
    from {{ ref('stg_categories') }}

)

, base as (

    select
        category_id
        , parent_category_id
        , is_active
        , trim(category_name) as category_name
        , lower(trim(slug)) as slug
    from source
    where category_id is not null

)

, deduplicated as (

    select
        *
        , row_number() over (
            partition by category_id
            order by category_id
        ) as record_rank
    from base

)

select
    category_id
    , category_name
    , slug
    , parent_category_id
    , is_active

from deduplicated
where record_rank = 1
