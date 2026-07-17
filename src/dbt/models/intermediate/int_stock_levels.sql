with source as (
    select
        product_variant_id
        , location_id
        , quantity_on_hand
        , reorder_point
    from {{ ref('stg_stock_levels') }}
)

, final as (
    select
        product_variant_id
        , location_id
        , quantity_on_hand
        , reorder_point
        , case
            when quantity_on_hand = 0 then true
            else false
        end as is_out_of_stock
    from source
)

select * from final