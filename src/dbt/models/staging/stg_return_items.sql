-- stg_return_items.sql

with source as (

    select *
    from {{ source('bronze', 'return_items') }}

)

select
    cast(id as integer) as return_item_id
    , cast(return_id as integer) as return_id
    , cast(order_item_id as integer) as order_item_id
    , cast(round(quantity, 2) as decimal(10, 2)) as quantity_returned
    , action
    , exchange_variant_id
    , unit_refund_amount

from source
