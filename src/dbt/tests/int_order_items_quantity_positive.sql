select
    order_item_id
    , order_id
    , quantity_ordered
from {{ ref('int_order_items') }}
where quantity_ordered <= 0
