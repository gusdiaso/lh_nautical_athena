-- stg_purchase_orders.sql

with source as (

    select *
    from {{ source('bronze', 'purchase_orders') }}

)

select
    cast(id as integer) as purchase_order_id
    , po_number
    , cast(supplier_id as integer) as supplier_id
    , cast(buyer_id as integer) as buyer_id
    , cast(destination_location_id as integer) as destination_location_id
    , status
    , currency
    , subtotal
    , total as original_total
    , cast(placed_at as timestamp) as placed_at
    , cast(expected_delivery_at as date) as expected_delivery_at

from source
