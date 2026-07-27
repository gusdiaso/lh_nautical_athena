-- Verifica que as taxas de câmbio são positivas, a taxa de compra não excede a de venda, e o spread não é negativo.
-- Falha quando há valores inválidos nas taxas, evitando cálculos financeiros incorretos em conversões monetárias.
select
    exchange_date
    , currency_code
    , exchange_rate_buy
    , exchange_rate_sell
    , average_exchange_rate
    , exchange_rate_spread
from {{ ref('int_exchange_rates') }}
where
    exchange_rate_buy <= 0
    or exchange_rate_sell <= 0
    or exchange_rate_buy > exchange_rate_sell
    or average_exchange_rate <= 0
    or exchange_rate_spread < 0
