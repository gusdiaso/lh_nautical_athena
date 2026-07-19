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
        , coalesce(expected_delivery_at, date_add(cast(placed_at as date), 30)) as expected_delivery_at
    from deduplicated
    where record_rank = 1

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
    , case
        when ranked.currency = 'BRL' then ranked.original_total
        else round(ranked.original_total * coalesce(er.average_exchange_rate, 0), 2)
    end as total_brl
    , placed_at
    , expected_delivery_at
from ranked
left join {{ ref('int_exchange_rates') }} as er
    on ranked.currency = er.currency_code
    and cast(ranked.placed_at as date) = er.exchange_date
