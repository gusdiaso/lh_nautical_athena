select
    return_id,
    total_refund_amount,
    has_refund_amount
from {{ ref('int_returns') }}
where
    (total_refund_amount > 0 and has_refund_amount = false)
    or
    (total_refund_amount = 0 and has_refund_amount = true)
    or total_refund_amount < 0