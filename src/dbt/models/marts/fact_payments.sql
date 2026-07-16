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
    {{ sk_from_keys(['coalesce(orders.customer_id, payments.order_id)']) }} as sk_customer,
    {{ sk_from_keys(['orders.salesperson_id']) }} as sk_employee,
    payments.payment_id,
    payments.order_id,
    payments.method,
    payments.installments,
    payments.amount,
    payments.status,
    payments.paid_at

from payments
left join orders
    on payments.order_id = orders.order_id
where payments.payment_id is not null