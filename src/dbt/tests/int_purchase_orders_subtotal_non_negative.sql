select
    purchase_order_id
    , po_number
    , subtotal
from {{ ref('int_purchase_orders') }}
where subtotal < 0
