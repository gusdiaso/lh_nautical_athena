select
    purchase_order_item_id
    , purchase_order_id
    , line_total
from {{ ref('int_purchase_order_items') }}
where line_total < 0
