-- Verifica que a data de entrega esperada é posterior à data de emissão do pedido.
-- Falha quando expected_delivery_at é menor ou igual a placed_at, evitando prazos de entrega logicamente impossíveis.
select
    purchase_order_id
    , po_number
    , placed_at
    , expected_delivery_at
from {{ ref('int_purchase_orders') }}
where expected_delivery_at <= placed_at
