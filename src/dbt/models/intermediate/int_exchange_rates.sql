with exchange_rates as (

    select *
    from {{ ref('stg_exchange_rates') }}

)

select
    exchange_date,
    currency_code,
    exchange_rate_buy,
    exchange_rate_sell,

    round(
        (exchange_rate_buy + exchange_rate_sell) / 2,
        6
    ) as average_exchange_rate,

    round(
        exchange_rate_sell - exchange_rate_buy,
        6
    ) as exchange_rate_spread

from exchange_rates