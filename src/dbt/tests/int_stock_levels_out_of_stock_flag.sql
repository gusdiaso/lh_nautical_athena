select *
from {{ ref('int_stock_levels') }}
where
    (quantity_on_hand = 0 and is_out_of_stock = false)
    or
    (quantity_on_hand > 0 and is_out_of_stock = true)