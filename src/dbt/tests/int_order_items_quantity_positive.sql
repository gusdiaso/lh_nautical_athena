-- Verifica que a quantidade pedida nos itens de pedido é positiva.
-- Falha quando quantity_ordered é zero ou negativo, evitando pedidos sem itens ou com quantidades inválidas.
select
    order_item_id
    , order_id
    , quantity_ordered
from {{ ref('int_order_items') }}
where quantity_ordered <= 0
