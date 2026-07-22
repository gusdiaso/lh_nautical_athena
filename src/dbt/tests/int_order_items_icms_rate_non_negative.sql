select
    order_item_id
    , order_id
    , icms_rate
from {{ ref('int_order_items') }}
where icms_rate < 0
