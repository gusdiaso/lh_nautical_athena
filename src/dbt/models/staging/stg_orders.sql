with source as (

    select *
    from {{ source('bronze', 'orders') }}

)

select
    id as order_id
    , order_number
    , channel
    , customer_id
    , salesperson_id
    , location_id
    , status
    , subtotal
    , discount_amount
    , total
    , placed_at

from source
