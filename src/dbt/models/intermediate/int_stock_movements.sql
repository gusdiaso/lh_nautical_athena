with source as (
    select
        stock_movement_id
        , product_variant_id
        , location_id
        , quantity
        , reference_id
        , employee_id
        , occurred_at
        , lower(trim(movement_type)) as movement_type
        , lower(trim(reference_table)) as reference_table
        , nullif(trim(notes), '') as notes
    from {{ ref('stg_stock_movements') }}
)

, final as (
    select
        stock_movement_id
        , product_variant_id
        , location_id
        , movement_type
        , round(quantity, 2) as quantity
        , reference_table
        , reference_id
        , employee_id
        , occurred_at
        , case
            when movement_type in ('purchase_in', 'return_in')
                then 'entrada'
            when movement_type in ('sale_out', 'return_out')
                then 'saida'
            else 'nao_classificado'
        end as movement_direction
        , coalesce(
            lower(coalesce(notes, ''))
            like '%opening balance%system migration%'
            , false
        ) as is_legacy_migration
    from source
)

select * from final
