with source as (

    select *
    from {{ ref('int_customers') }}

)

select
    {{ sk_from_keys(['customer_id']) }} as sk_customer,
    customer_id,
    person_type,
    legal_name,
    trade_name,
    tax_id,
    state_registration,
    email,
    phone,
    is_active

from source
where customer_id is not null