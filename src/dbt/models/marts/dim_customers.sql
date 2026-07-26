-- ============================================================
-- dim_customers.sql
-- Grão:
-- uma linha por cliente cadastrado
-- + membro técnico para cliente não informado
--
-- Quando houver mais de um endereço, é utilizado o endereço
-- principal. Na ausência dele, é selecionado um endereço de
-- forma determinística para manter uma linha por cliente.
-- ============================================================

with customers as (
    select
        customer_id
        , person_type
        , legal_name
        , trade_name
        , tax_id
        , state_registration
        , email
        , phone
        , is_active
    from {{ ref('int_customers') }}
)

, addresses as (
    select
        address_id
        , customer_id
        , address_type
        , postal_code
        , street
        , number
        , complement
        , district
        , city
        , state
        , country
        , is_primary
        , row_number() over (
            partition by customer_id
            order by
                is_primary desc
                , address_id asc
        ) as address_rank
    from {{ ref('int_addresses') }}
)

, selected_addresses as (
    select
        address_id
        , customer_id
        , address_type
        , postal_code
        , street
        , number
        , complement
        , district
        , city
        , state
        , country
        , is_primary
    from addresses
    where address_rank = 1
)

, technical_customer as (
    select
        cast(-1 as bigint) as nk_customer_id
        , cast(null as string) as person_type
        , 'Cliente não informado' as legal_name
        , cast(null as string) as trade_name
        , cast(null as string) as tax_id
        , cast(null as string) as state_registration
        , cast(null as string) as email
        , cast(null as string) as phone
        , cast(null as bigint) as nk_address_id
        , cast(null as string) as address_type
        , cast(null as string) as postal_code
        , cast(null as string) as street
        , cast(null as string) as number
        , cast(null as string) as complement
        , cast(null as string) as district
        , cast(null as string) as city
        , cast(null as string) as state
        , cast(null as string) as country
        , false as is_primary_address
        , false as is_active
        , true as is_technical_member
        , md5('customer||nao_informado') as sk_customer
)

, customers_dimension as (
    select
        customers.customer_id as nk_customer_id
        , customers.person_type
        , customers.legal_name
        , customers.trade_name
        , customers.tax_id
        , customers.state_registration
        , customers.email
        , customers.phone
        , selected_addresses.address_id as nk_address_id
        , selected_addresses.address_type
        , selected_addresses.postal_code
        , selected_addresses.street
        , selected_addresses.number
        , selected_addresses.complement
        , selected_addresses.district
        , selected_addresses.city
        , selected_addresses.state
        , selected_addresses.country
        , customers.is_active
        , false as is_technical_member
        , {{ sk_from_keys(["'customer'", 'customers.customer_id']) }} as sk_customer
        , coalesce(selected_addresses.is_primary, false) as is_primary_address
    from customers
    left join selected_addresses
        on customers.customer_id = selected_addresses.customer_id
)

, final as (
    select
        sk_customer
        , nk_customer_id
        , person_type
        , legal_name
        , trade_name
        , tax_id
        , state_registration
        , email
        , phone
        , nk_address_id
        , address_type
        , postal_code
        , street
        , number
        , complement
        , district
        , city
        , state
        , country
        , is_primary_address
        , is_active
        , is_technical_member
    from technical_customer

    union all

    select
        sk_customer
        , nk_customer_id
        , person_type
        , legal_name
        , trade_name
        , tax_id
        , state_registration
        , email
        , phone
        , nk_address_id
        , address_type
        , postal_code
        , street
        , number
        , complement
        , district
        , city
        , state
        , country
        , is_primary_address
        , is_active
        , is_technical_member
    from customers_dimension
)

select * from final
