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
