with source as (

    select *
    from {{ source('bronze', 'categories') }}

)

select
    id as category_id,
    name,
    slug,
    parent_category_id,
    is_active,
    created_at,
    updated_at

from source