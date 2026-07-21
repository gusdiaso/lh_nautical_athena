select
    purchase_order_id
    , po_number
    , original_total
    , currency
    , total_brl
from {{ ref('int_purchase_orders') }}
where total_brl <= 0
