-- Verifica que a flag has_refund_amount é consistente com o total_refund_amount e que este não é negativo.
-- Falha quando a flag não reflete o valor de reembolso ou quando o valor é negativo, evitando sinalização incorreta de reembolso.
select
    return_id
    , total_refund_amount
    , has_refund_amount
from {{ ref('int_returns') }}
where
    (total_refund_amount > 0 and has_refund_amount = false)
    or
    (total_refund_amount = 0 and has_refund_amount = true)
    or total_refund_amount < 0
