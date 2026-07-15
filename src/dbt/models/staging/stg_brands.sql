with source as (

    select *
    from {{ source('bronze', 'brands') }}

)

select
    id as brand_id
    , name as brand_name
    , country
    , is_active

from source
