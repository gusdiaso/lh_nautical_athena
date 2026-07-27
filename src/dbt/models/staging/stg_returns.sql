with source as (
    select *
    from {{ source('bronze', 'returns') }}
)

, final as (
    select
        id as return_id
        , return_number
        , order_id
        , customer_id
        , received_at_location_id
        , status
        , reason as original_reason
        , total_refund_amount
        , cast(created_at as timestamp) as created_at
        , lower(trim(reason)) as reason_normalized
    from source
)

select * from final
