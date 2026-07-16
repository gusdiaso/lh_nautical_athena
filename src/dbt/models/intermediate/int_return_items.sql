with source as (

    select *
    from {{ ref('stg_return_items') }}

)

select
    return_item_id
    , return_id
    , order_item_id
    , quantity_returned
    , action
    , exchange_variant_id
    , unit_refund_amount
    , action = 'exchange' as is_exchange
    , action = 'refund' as is_refund
    , case
        when action = 'refund'
            then quantity_returned * unit_refund_amount
        else 0.00
    end as total_line_refund_amount

from source
where return_item_id is not null
