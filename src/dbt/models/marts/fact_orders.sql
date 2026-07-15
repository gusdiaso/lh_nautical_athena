with source as (

    select *
    from {{ ref('int_orders') }}

)

select
    cast(date_format(placed_at, 'yyyyMMdd') as string) as sk_date,
    md5(cast(customer_id as string)) as sk_customer,
    md5(cast(salesperson_id as string)) as sk_employee,
    order_id,
    order_number,
    channel,
    customer_id,
    salesperson_id,
    location_id,
    status,
    subtotal,
    discount_amount,
    total,
    placed_at

from source
where order_id is not null