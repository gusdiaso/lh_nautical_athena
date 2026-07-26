-- Verifica que o total em BRL dos pedidos de compra é positivo.
-- Falha quando total_brl é zero ou negativo, evitando valores totais convertidos inválidos.
select
    purchase_order_id
    , po_number
    , currency
    , total_brl
from {{ ref('int_purchase_orders') }}
where total_brl <= 0
