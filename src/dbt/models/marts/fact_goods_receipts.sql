with source as (

    select *
    from {{ ref('int_goods_receipts') }}

)

select
    cast(date_format(received_at, 'yyyyMMdd') as string) as sk_date,
    {{ sk_from_keys(['received_by_employee_id']) }} as sk_employee,
    goods_receipt_id,
    purchase_order_id,
    received_by_employee_id,
    received_at,
    notes

from source
where goods_receipt_id is not null