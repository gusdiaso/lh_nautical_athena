-- Verifica que payment_status é consistente com os valores monetários e as flags booleanas de estado.
-- Falha quando há contradição entre status textual, valores pagos/reembolsados e flags, evitando classificações de pagamento incorretas.
select
    nk_payment_id as payment_id
    , payment_status
    , payment_amount
    , paid_amount
    , refunded_amount
    , is_paid
    , is_refunded
    , is_pending
    , is_cancelled
from {{ ref('fact_payments') }}
where
    (
        payment_status = 'approved'
        and (
            paid_amount <> payment_amount
            or refunded_amount <> 0
            or not is_paid
            or is_refunded
            or is_pending
            or is_cancelled
        )
    )
    or (
        payment_status = 'refunded'
        and (
            refunded_amount <> payment_amount
            or paid_amount <> 0
            or not is_refunded
            or is_paid
            or is_pending
            or is_cancelled
        )
    )
    or (
        payment_status = 'pending'
        and (
            paid_amount <> 0
            or refunded_amount <> 0
            or not is_pending
            or is_paid
            or is_refunded
            or is_cancelled
        )
    )
    or (
        payment_status = 'cancelled'
        and (
            paid_amount <> 0
            or refunded_amount <> 0
            or not is_cancelled
            or is_paid
            or is_refunded
            or is_pending
        )
    )
