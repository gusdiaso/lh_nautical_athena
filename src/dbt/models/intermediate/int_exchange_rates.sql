with exchange_rates as (

    select
        exchange_date
        , currency_code
        , cast(exchange_rate_buy as decimal(18, 6)) as exchange_rate_buy
        , cast(exchange_rate_sell as decimal(18, 6)) as exchange_rate_sell
    from {{ ref('stg_exchange_rates') }}

)

, final as (

    select
        exchange_date
        , currency_code
        , exchange_rate_buy
        , exchange_rate_sell
        , cast(
            round(
                (exchange_rate_buy + exchange_rate_sell) / 2
                , 6
            ) as decimal(18, 6)
        ) as average_exchange_rate
        , cast(
            round(
                exchange_rate_sell - exchange_rate_buy
                , 6
            ) as decimal(18, 6)
        ) as exchange_rate_spread
    from exchange_rates

)

select *
from final
