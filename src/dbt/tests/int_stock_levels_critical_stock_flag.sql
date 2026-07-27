-- Verifica que a flag is_critical_stock é verdadeira quando quantity_on_hand está zerado,
-- negativo ou abaixo do reorder_point.
-- Falha quando há inconsistência entre saldo real e flag, evitando alertas incorretos.
select *
from {{ ref('int_stock_levels') }}
where
    ((quantity_on_hand <= 0 or quantity_on_hand < reorder_point) and is_critical_stock = false)
    or
    (quantity_on_hand > 0 and quantity_on_hand >= reorder_point and is_critical_stock = true)
