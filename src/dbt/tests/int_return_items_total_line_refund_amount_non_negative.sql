-- Verifica que o valor total de reembolso por linha de item de retorno não é negativo.
-- Falha quando total_line_refund_amount é negativo, evitando valores de reembolso inconsistentes.
select
    return_item_id
    , return_id
    , total_line_refund_amount
from {{ ref('int_return_items') }}
where total_line_refund_amount < 0
