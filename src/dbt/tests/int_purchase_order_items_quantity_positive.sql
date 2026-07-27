-- Verifica que a quantidade pedida nos itens de pedido de compra é positiva.
-- Falha quando quantity_ordered é zero ou negativo, evitando pedidos de compra sem itens.
select
    purchase_order_item_id
    , purchase_order_id
    , quantity_ordered
from {{ ref('int_purchase_order_items') }}
where quantity_ordered <= 0
