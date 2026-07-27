with source as (
    select
        return_item_id
        , return_id
        , order_item_id
        , quantity_returned
        , exchange_variant_id
        , unit_refund_amount
        , lower(trim(action)) as action
    from {{ ref('stg_return_items') }}
    where return_item_id is not null
)

, deduplicated as (
    select
        return_item_id
        , return_id
        , order_item_id
        , quantity_returned
        , action
        , exchange_variant_id
        , unit_refund_amount
        , row_number() over (
            partition by return_item_id
            order by return_item_id
        ) as record_rank
    from source
)

, classified as (
    select
        return_item_id
        , return_id
        , order_item_id
        , quantity_returned
        , action
        , exchange_variant_id
        , unit_refund_amount
        , case
            when action = 'refund'
                then round(
                    quantity_returned * coalesce(unit_refund_amount, 0)
                    , 2
                )
            else 0.00
        end as total_line_refund_amount
        , action = 'exchange' as is_exchange
        , action = 'refund' as is_refund
    from deduplicated
    where record_rank = 1
)

, final as (
    select
        return_item_id
        , return_id
        , order_item_id
        , quantity_returned
        , action
        , exchange_variant_id
        , unit_refund_amount
        , is_exchange
        , is_refund
        , total_line_refund_amount
    from classified
)

select * from final
