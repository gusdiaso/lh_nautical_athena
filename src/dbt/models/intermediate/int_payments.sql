with source as (

    select *
    from {{ ref('stg_payments') }}

),

base as (

    select
        payment_id,
        order_id,
        lower(trim(method)) as method,
        installments,
        amount,
        lower(trim(status)) as status,
        paid_at
    from source
    where payment_id is not null

),

deduplicated as (

    select
        *,
        row_number() over (
            partition by payment_id
            order by payment_id
        ) as record_rank
    from base

)

select
    payment_id,
    order_id,
    method,
    installments,
    amount,
    status,
    paid_at

from deduplicated
where record_rank = 1