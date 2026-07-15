with source as (

    select *
    from {{ source('bronze', 'customers') }}

)

select
    id as customer_id
    , person_type
    , legal_name
    , trade_name
    , tax_id
    , state_registration
    , email
    , phone
    , is_active

from source
