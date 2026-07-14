-- stg_purchase_orders.sql

with source as (

    select *
    from {{ source('bronze', 'purchase_orders') }}

)

select
    id as purchase_order_id
    , po_number
    , supplier_id
    , buyer_id
    , destination_location_id
    , status
    , currency
    , subtotal
    , total
    , placed_at
    , expected_delivery_at

from source
