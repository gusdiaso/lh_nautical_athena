select
    purchase_order_item_id
    , purchase_order_id
    , unit_cost
from {{ ref('int_purchase_order_items') }}
where unit_cost < 0
