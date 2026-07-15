with stock_movements as (

    select *
    from {{ ref('stg_stock_movements') }}

)

select
    stock_movement_id
    , product_variant_id
    , location_id
    , movement_type
    , quantity

    , reference_table

    , reference_id

    , employee_id
    , notes
    , occurred_at
    , created_at

    , case
        when movement_type in ('purchase_in', 'return_in')
            then 'entrada'

        when movement_type in ('sale_out', 'return_out')
            then 'saida'

        else 'nao_classificado'
    end as movement_direction

    , abs(quantity) as absolute_quantity
    , coalesce(
        lower(coalesce(notes, ''))
        like '%opening balance%system migration%', false
    ) as is_legacy_migration

from stock_movements
