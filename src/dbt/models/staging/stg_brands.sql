with source as (

    select *
    from {{ source('bronze', 'brands') }}

)

select
    id as brand_id
    , name
    , country
    , is_active
    

from source
