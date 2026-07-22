select
    order_item_id
    , order_id
    , original_line_total
    , total_with_taxes
from {{ ref('int_order_items') }}
where total_with_taxes <= 0
