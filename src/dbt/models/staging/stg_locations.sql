-- stg_locations.sql

with source as (

    select *
    from {{ source('bronze', 'locations') }}

)

select
    id as location_id
    , location_name
    , location_type
    , postal_code
    , street
    , number
    , complement
    , district
    , city
    , state
    , country
    , is_active
    , created_at
    , updated_at

from source
