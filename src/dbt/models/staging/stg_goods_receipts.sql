with source as (

    select *
    from {{ source('bronze', 'goods_receipts') }}

)

select
    id as goods_receipt_id
    , purchase_order_id
    , received_by_employee_id
    , received_at
    , notes

from source
