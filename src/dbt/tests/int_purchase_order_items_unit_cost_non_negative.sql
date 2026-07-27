-- Verifica que o custo unitário dos itens de pedido de compra não é negativo.
-- Falha quando unit_cost é negativo, evitando custos de aquisição inconsistentes.
select
    purchase_order_item_id
    , purchase_order_id
    , unit_cost
from {{ ref('int_purchase_order_items') }}
where unit_cost < 0
