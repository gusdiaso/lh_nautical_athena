with source as (

    select *
    from {{ ref('stg_customers') }}

)

, base as (

    select
        customer_id
        , is_active
        , lower(trim(person_type)) as person_type
        , trim(legal_name) as legal_name
        , trim(trade_name) as trade_name
        , trim(tax_id) as tax_id
        , trim(state_registration) as state_registration
        , lower(trim(email)) as email
        , trim(phone) as phone
    from source
    where customer_id is not null

)

, deduplicated as (

    select
        *
        , row_number() over (
            partition by customer_id
            order by customer_id
        ) as record_rank
    from base

)

select
    customer_id
    , person_type
    , legal_name
    , trade_name
    , tax_id
    , state_registration
    , email
    , phone
    , is_active

from deduplicated
where record_rank = 1
