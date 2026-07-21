select
    nk_purchase_order_item_id as purchase_order_item_id
    , currency
    , exchange_rate_sell
    , unit_cost_original_currency
    , line_total_original_currency
    , unit_cost_brl
    , line_total_brl
    , expected_delivery_at
    , is_expected_delivery_overdue
from {{ ref('fact_purchase_order_items') }}
where
    (
        currency = 'BRL'
        and (
            unit_cost_brl <> unit_cost_original_currency
            or line_total_brl <> line_total_original_currency
        )
    )
    or (
        currency <> 'BRL'
        and exchange_rate_sell is not null
        and (
            round(unit_cost_original_currency * exchange_rate_sell, 2) <> unit_cost_brl
            or round(line_total_original_currency * exchange_rate_sell, 2) <> line_total_brl
        )
    )
    or (
        expected_delivery_at < current_date()
        and is_expected_delivery_overdue = false
    )
    or (
        expected_delivery_at >= current_date()
        and is_expected_delivery_overdue = true
    )
