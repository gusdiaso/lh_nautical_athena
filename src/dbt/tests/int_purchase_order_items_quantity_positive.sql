select
    purchase_order_item_id
    , purchase_order_id
    , quantity_ordered
from {{ ref('int_purchase_order_items') }}
where quantity_ordered <= 0
