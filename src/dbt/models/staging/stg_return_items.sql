-- stg_return_items.sql

with source as (

    select *
    from {{ source('bronze', 'return_items') }}

)

select
    id as return_item_id
    , return_id
    , order_item_id
    , quantity
    , action
    , exchange_variant_id
    , unit_refund_amount

from source
