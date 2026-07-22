select
    nk_order_item_id as order_item_id
    , nk_order_id as order_id
    , gross_line_total
    , allocated_discount_amount
    , net_line_total
    , quantity_ordered
    , unit_price
    , standard_unit_cost
    , estimated_cost_of_goods_sold
    , estimated_gross_profit
from {{ ref('fact_order_items') }}
where round(gross_line_total - allocated_discount_amount, 2) <> net_line_total
   or allocated_discount_amount < 0
   or gross_line_total < 0
   or (
       standard_unit_cost is not null
       and round(quantity_ordered * standard_unit_cost, 2) <> estimated_cost_of_goods_sold
   )
   or (
       standard_unit_cost is not null
       and round(net_line_total - estimated_cost_of_goods_sold, 2) <> estimated_gross_profit
   )
