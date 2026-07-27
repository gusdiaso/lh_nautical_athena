-- Verifica que a alíquota de IPI não é negativa.
-- Falha quando ipi_rate é negativo, evitando alíquotas de imposto inconsistentes.
select
    order_item_id
    , order_id
    , ipi_rate
from {{ ref('int_order_items') }}
where ipi_rate < 0
