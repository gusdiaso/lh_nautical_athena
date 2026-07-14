-- stg_returns.sql

with source as (

    select *
    from {{ source('bronze', 'returns') }}

)

select
    id as return_id
    , return_number
    , order_id
    , customer_id
    , received_at_location_id
    , status
    , total_refund_amount
    , created_at
    , updated_at
    , lower(trim(reason)) as reason

from source
