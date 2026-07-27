-- Verifica que a alíquota de ICMS não é negativa.
-- Falha quando icms_rate é negativo, evitando alíquotas de imposto inconsistentes.
select
    order_item_id
    , order_id
    , icms_rate
from {{ ref('int_order_items') }}
where icms_rate < 0
