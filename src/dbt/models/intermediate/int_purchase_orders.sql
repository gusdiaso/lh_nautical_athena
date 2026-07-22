with source as (

    select *
    from {{ ref('stg_purchase_orders') }}

)

, base as (

    select
        purchase_order_id
        , supplier_id
        , buyer_id
        , destination_location_id
        , subtotal
        , original_total
        , placed_at
        , expected_delivery_at
        , trim(po_number) as po_number
        , lower(trim(status)) as status
        , upper(trim(currency)) as currency
    from source
    where purchase_order_id is not null

)

, deduplicated as (

    select
        *
        , row_number() over (
            partition by purchase_order_id
            order by placed_at desc nulls last
        ) as record_rank
    from base

)

, ranked as (

    select
        purchase_order_id
        , po_number
        , supplier_id
        , buyer_id
        , destination_location_id
        , status
        , currency
        , subtotal
        , original_total
        , placed_at
        , coalesce(
            expected_delivery_at, date_add(cast(placed_at as date), 30)
        ) as expected_delivery_at
    from deduplicated
    where record_rank = 1

)

, exchange_rate_ranges as (

    select
        currency_code
        , exchange_date as valid_from
        , exchange_rate_buy
        , exchange_rate_sell
        , average_exchange_rate
        , exchange_rate_spread
        , coalesce(
            lead(exchange_date)
                over (
                    partition by currency_code
                    order by exchange_date
                )
            , cast('9999-12-31' as date)
        ) as valid_to
    from {{ ref('int_exchange_rates') }}

)

select
    purchase_order_id
    , po_number
    , supplier_id
    , buyer_id
    , destination_location_id
    , status
    , currency
    , er.exchange_rate_sell
    , subtotal
    , original_total
    , placed_at
    , expected_delivery_at
    , case
        when ranked.currency = 'BRL' then ranked.original_total
        else round(ranked.original_total * er.average_exchange_rate, 2)
    end as total_brl
from ranked
left join exchange_rate_ranges as er
    on
        ranked.currency = er.currency_code
        and cast(ranked.placed_at as date) >= er.valid_from
        and cast(ranked.placed_at as date) < er.valid_to
