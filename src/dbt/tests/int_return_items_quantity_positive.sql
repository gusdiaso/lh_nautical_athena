select
    return_item_id
    , return_id
    , quantity_returned
from {{ ref('int_return_items') }}
where quantity_returned <= 0
