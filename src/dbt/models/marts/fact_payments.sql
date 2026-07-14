with payments as (

    select *
    from {{ ref('int_payments') }}

),

orders as (

    select
        order_id,
        customer_id,
        salesperson_id
    from {{ ref('int_orders') }}

)

select
    cast(date_format(paid_at, 'yyyyMMdd') as string) as sk_date,
    md5(cast(coalesce(orders.customer_id, payments.order_id) as string)) as sk_customer,
    md5(cast(orders.salesperson_id as string)) as sk_employee,
    payments.payment_id,
    payments.order_id,
    payments.method,
    payments.installments,
    payments.amount,
    payments.status,
    payments.paid_at,
    payments.created_at,
    payments.updated_at

from payments
left join orders
    on payments.order_id = orders.order_id
where payments.payment_id is not null