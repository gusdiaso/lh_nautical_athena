select
    return_item_id
    , return_id
    , total_line_refund_amount
from {{ ref('int_return_items') }}
where total_line_refund_amount < 0
