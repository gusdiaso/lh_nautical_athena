-- Verifica que o subtotal dos pedidos de compra não é negativo.
-- Falha quando subtotal é negativo, evitando valores financeiros inconsistentes no pedido.
select
    purchase_order_id
    , po_number
    , subtotal
from {{ ref('int_purchase_orders') }}
where subtotal < 0
