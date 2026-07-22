select
    goods_receipt_item_id
    , goods_receipt_id
    , quantity_received
from {{ ref('int_goods_receipt_items') }}
where quantity_received <= 0
