with source as (

    select *
    from {{ ref('stg_orders') }}

)

, base as (

    select
        order_id
        , customer_id
        , salesperson_id
        , location_id
        , subtotal
        , discount_amount
        , total
        , placed_at
        , created_at
        , updated_at
        , trim(order_number) as order_number
        , lower(trim(channel)) as channel
        , lower(trim(status)) as status
    from source
    where order_id is not null

)

, deduplicated as (

    select
        *
        , row_number() over (
            partition by order_id
            order by updated_at desc nulls last, created_at desc nulls last
        ) as record_rank
    from base

)

select
    order_id
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
    , created_at
    , updated_at

from deduplicated
where record_rank = 1
