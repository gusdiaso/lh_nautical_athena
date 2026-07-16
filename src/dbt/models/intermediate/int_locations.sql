with source as (

    select *
    from {{ ref('stg_locations') }}

)

, base as (

    select
        location_id
        , trim(location_name) as location_name
        , lower(trim(location_type)) as location_type
        , {{ clean_cep('postal_code') }} as postal_code
        , trim(street) as street
        , trim(number) as number
        , trim(complement) as complement
        , trim(district) as district
        , trim(city) as city
        , trim(state) as state
        , trim(country) as country
        , is_active
    from source
    where location_id is not null

)

, deduplicated as (

    select
        *
        , row_number() over (
            partition by location_id
            order by location_id
        ) as record_rank
    from base

)

select
    location_id
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

from deduplicated
where record_rank = 1
