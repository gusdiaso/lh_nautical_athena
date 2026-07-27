-- Verifica que pedidos em moeda estrangeira já realizados possuem conversão para BRL.
-- Falha quando total_brl é nulo para pedidos não em BRL com data passada, evitando valores sem conversão cambial.
select
    purchase_order_id
    , po_number
    , currency
    , total_brl
    , placed_at
from {{ ref('int_purchase_orders') }}
where currency != 'BRL'
  and total_brl is null
  and cast(placed_at as date) < current_date
