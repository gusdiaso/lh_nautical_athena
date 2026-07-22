select
    return_item_id
    , return_id
    , unit_refund_amount
    , action
from {{ ref('int_return_items') }}
where unit_refund_amount < 0
