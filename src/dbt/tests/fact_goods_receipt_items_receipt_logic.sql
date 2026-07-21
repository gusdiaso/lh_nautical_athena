select
    goods_receipt_item_id
    , currency
    , exchange_rate_sell
    , quantity_ordered
    , quantity_received
    , cumulative_quantity_received
    , remaining_quantity_after_receipt
    , is_fully_received
    , is_partial_receipt
    , unit_cost_original_currency
    , received_value_original_currency
    , received_value_brl
    , expected_delivery_at
    , received_at
    , delivery_variance_days
    , is_late_receipt
from {{ ref('fact_goods_receipt_items') }}
where
    round(quantity_received * unit_cost_original_currency, 2)
        <> received_value_original_currency
    or (
        currency = 'BRL'
        and received_value_brl <> received_value_original_currency
    )
    or (
        currency <> 'BRL'
        and exchange_rate_sell is not null
        and round(
            quantity_received * unit_cost_original_currency * exchange_rate_sell,
            2
        ) <> received_value_brl
    )
    or remaining_quantity_after_receipt <> greatest(
        quantity_ordered - cumulative_quantity_received,
        0
    )
    or is_fully_received <> (cumulative_quantity_received >= quantity_ordered)
    or is_partial_receipt <> (cumulative_quantity_received < quantity_ordered)
    or delivery_variance_days <> datediff(cast(received_at as date), expected_delivery_at)
    or is_late_receipt <> (cast(received_at as date) > expected_delivery_at)
