-- stg_exchange_rates.sql

with source as (

    select *
    from {{ source('bronze', 'exchange_rates') }}

)

select
    exchange_date
    , currency_code
    , exchange_rate_buy
    , exchange_rate_sell

from source
