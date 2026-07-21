select
    return_item_id
    , action
    , sk_exchange_product
    , is_exchange
    , is_refund
    , returned_item_count
from {{ ref('fact_return_items') }}
where
    (action = 'refund' and sk_exchange_product is not null)
    or (action = 'exchange' and sk_exchange_product is null)
    or (action = 'refund' and is_exchange)
    or (action = 'exchange' and is_refund)
    or returned_item_count <> 1
