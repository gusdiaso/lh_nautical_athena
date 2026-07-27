-- Verifica que o preço unitário dos itens de pedido é positivo.
-- Falha quando unit_price é zero ou negativo, evitando vendas com preço inválido.
select
    order_item_id
    , order_id
    , unit_price
from {{ ref('int_order_items') }}
where unit_price <= 0
