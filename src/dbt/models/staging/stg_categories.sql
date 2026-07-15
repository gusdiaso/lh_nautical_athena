with source as (

    select *
    from {{ source('bronze', 'categories') }}

)

select
    id as category_id
    , name
    , slug
    , parent_category_id
    , is_active
    

from source
