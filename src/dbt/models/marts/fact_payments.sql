-- ============================================================
-- fact_payments.sql
-- Grão:
-- uma linha por transação de pagamento
--
-- Um pagamento está relacionado ao pedido e ao cliente.
-- Não existe relacionamento direto com produto porque um
-- pagamento pode liquidar um pedido contendo vários SKUs.
--
-- A data do pedido e a data efetiva de pagamento são mantidas
-- como papéis diferentes da mesma dimensão calendário.
-- ============================================================

with payments as (
    select
        payment_id
        , order_id
        , method
        , installments
        , amount
        , status
        , paid_at
    from {{ ref('int_payments') }}
)

, orders as (
    select
        order_id
        , order_number
        , channel
        , customer_id
        , location_id
        , status
        , total
        , placed_at
    from {{ ref('int_orders') }}
)

, customers as (
    select
        sk_customer
        , nk_customer_id
    from {{ ref('dim_customers') }}
)

, locations as (
    select
        sk_location
        , nk_location_id
    from {{ ref('dim_locations') }}
)

, dates as (
    select
        sk_date
        , full_date
    from {{ ref('dim_date') }}
)

, joined as (
    select
        payments.payment_id as nk_payment_id
        , payments.order_id as nk_order_id
        , orders.order_number
        , order_dates.sk_date as sk_order_date
        , payment_dates.sk_date as sk_payment_date
        , orders.channel
        , orders.status as order_status
        , payments.method
        , payments.installments
        , payments.amount as payment_amount
        , orders.total as order_total
        , payments.status as payment_status
        , orders.placed_at
        , payments.paid_at
        , cast(1 as integer) as payment_count
        , md5(
            concat_ws(
                '||'
                , 'payment'
                , cast(payments.payment_id as string)
            )
        ) as sk_payment
        , coalesce(
            customers.sk_customer
            , md5('customer||nao_informado')
        ) as sk_customer
        , coalesce(
            locations.sk_location
            , md5('location||nao_informada')
        ) as sk_location
        , payments.status = 'approved' as is_paid
        , payments.status = 'refunded' as is_refunded
        , payments.status = 'pending' as is_pending
        , payments.status = 'cancelled' as is_cancelled
        , case
            when payments.status = 'approved'
                then payments.amount
            else cast(0 as decimal(18, 2))
        end as paid_amount
        , case
            when payments.status = 'refunded'
                then payments.amount
            else cast(0 as decimal(18, 2))
        end as refunded_amount
    from payments
    inner join orders
        on payments.order_id = orders.order_id
    left join customers
        on orders.customer_id = customers.nk_customer_id
    left join locations
        on orders.location_id = locations.nk_location_id
    left join dates as order_dates
        on cast(orders.placed_at as date) = order_dates.full_date
    left join dates as payment_dates
        on cast(payments.paid_at as date) = payment_dates.full_date
)

, final as (
    select
        sk_payment
        , nk_payment_id
        , nk_order_id
        , order_number
        , sk_customer
        , sk_location
        , sk_order_date
        , sk_payment_date
        , channel
        , order_status
        , method
        , installments
        , payment_amount
        , order_total
        , payment_status
        , placed_at
        , paid_at
        , is_paid
        , is_refunded
        , is_pending
        , is_cancelled
        , paid_amount
        , refunded_amount
        , payment_count
    from joined
)

select * from final;
