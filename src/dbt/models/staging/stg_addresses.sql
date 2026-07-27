-- stg_addresses.sql

with source as (

    select *
    from {{ source('bronze', 'addresses') }}

)

select
    id as address_id
    , customer_id
    , address_type
    , postal_code
    , street
    , number
    , complement
    , district
    , city
    , state
    , country
    , is_primary

from source
