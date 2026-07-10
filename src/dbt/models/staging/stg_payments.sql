with source as (

    select *
    from {{ source('bronze', 'payments') }}

)

select
    id as payment_id,
    order_id,
    method,
    installments,
    amount,
    status,
    paid_at,
    created_at,
    updated_at

from source