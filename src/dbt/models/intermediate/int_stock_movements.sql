with source as (
    select
        stock_movement_id
        , product_variant_id
        , location_id
        , lower(trim(movement_type)) as movement_type
        , quantity
        , lower(trim(reference_table)) as reference_table
        , reference_id
        , employee_id
        , nullif(trim(notes), '') as notes
        , occurred_at
    from {{ ref('stg_stock_movements') }}
)

, final as (
    select
        stock_movement_id
        , product_variant_id
        , location_id
        , movement_type
        , case
            when movement_type in ('purchase_in', 'return_in')
                then 'entrada'
            when movement_type in ('sale_out', 'return_out')
                then 'saida'
            else 'nao_classificado'
        end as movement_direction
        , quantity
        , abs(quantity) as absolute_quantity
        , reference_table
        , reference_id
        , employee_id
        , notes
        , occurred_at
        , coalesce(
            lower(coalesce(notes, ''))
                like '%opening balance%system migration%'
            , false
        ) as is_legacy_migration
        , cast(occurred_at as date) > current_date()
            as is_future_movement
    from source
)

select * from final