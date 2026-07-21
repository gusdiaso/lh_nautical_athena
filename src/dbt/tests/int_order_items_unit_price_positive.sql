select
    order_item_id
    , order_id
    , unit_price
from {{ ref('int_order_items') }}
where unit_price <= 0
