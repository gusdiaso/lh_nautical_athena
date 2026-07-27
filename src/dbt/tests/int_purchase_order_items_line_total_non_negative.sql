-- Verifica que o total da linha dos itens de pedido de compra não é negativo.
-- Falha quando line_total é negativo, evitando valores totais de item inconsistentes.
select
    purchase_order_item_id
    , purchase_order_id
    , line_total
from {{ ref('int_purchase_order_items') }}
where line_total < 0
