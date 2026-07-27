-- Verifica que o valor unitário de reembolso dos itens de retorno não é negativo.
-- Falha quando unit_refund_amount é negativo, evitando valores de reembolso unitário inconsistentes.
select
    return_item_id
    , return_id
    , unit_refund_amount
    , action
from {{ ref('int_return_items') }}
where unit_refund_amount < 0
