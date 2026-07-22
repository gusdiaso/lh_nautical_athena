select
    order_item_id
    , order_id
    , ipi_rate
from {{ ref('int_order_items') }}
where ipi_rate < 0
