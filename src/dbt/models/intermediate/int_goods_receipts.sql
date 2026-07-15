with source as (

    select *
    from {{ ref('stg_goods_receipts') }}

),

base as (

    select
        goods_receipt_id,
        purchase_order_id,
        received_by_employee_id,
        received_at,
        trim(notes) as notes,
            notes
    from source
    where goods_receipt_id is not null

),

deduplicated as (

    select
        *,
        row_number() over (
            partition by goods_receipt_id
                order by goods_receipt_id
        ) as record_rank
    from base

)

select
    goods_receipt_id,
    purchase_order_id,
    received_by_employee_id,
    received_at,
        notes

from deduplicated
where record_rank = 1