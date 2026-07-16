with source as (

    select *
    from {{ ref('int_orders') }}

)

select
    cast(date_format(placed_at, 'yyyyMMdd') as string) as sk_date,
    {{ sk_from_keys(['customer_id']) }} as sk_customer,
    {{ sk_from_keys(['salesperson_id']) }} as sk_employee,
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