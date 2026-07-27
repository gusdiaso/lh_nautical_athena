-- Verifica que o total com impostos dos itens de pedido é positivo.
-- Falha quando total_with_taxes é zero ou negativo, evitando valores finais de venda inválidos.
select
    order_item_id
    , order_id
    , original_line_total
    , total_with_taxes
from {{ ref('int_order_items') }}
where total_with_taxes <= 0
