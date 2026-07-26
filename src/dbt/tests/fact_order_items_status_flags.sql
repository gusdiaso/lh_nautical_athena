-- Verifica que order_status é consistente com as flags booleanas de estado do pedido.
-- Falha quando o status textual não corresponde às flags ativas, evitando classificações conflitantes de pedido.
select
    nk_order_item_id as order_item_id
    , order_status
    , is_cancelled
    , is_paid
    , is_confirmed
    , is_draft
from {{ ref('fact_order_items') }}
where
    (
        order_status = 'cancelled'
        and (not is_cancelled or is_paid or is_confirmed or is_draft)
    )
    or (
        order_status = 'paid'
        and (not is_paid or is_cancelled or is_confirmed or is_draft)
    )
    or (
        order_status = 'confirmed'
        and (not is_confirmed or is_cancelled or is_paid or is_draft)
    )
    or (
        order_status = 'draft'
        and (not is_draft or is_cancelled or is_paid or is_confirmed)
    )
