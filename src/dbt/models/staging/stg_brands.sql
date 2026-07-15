with source as (

    select *
    from {{ source('bronze', 'brands') }}

)

select
    id as brand_id
    , name
    , country
    , is_active
    , created_at
    , updated_at

from source
