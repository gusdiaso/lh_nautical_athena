with stock_movements as (

    select *
    from {{ ref('stg_stock_movements') }}

)

select
    stock_movement_id,
    product_variant_id,
    location_id,
    movement_type,
    quantity,

    case
        when movement_type in ('purchase_in', 'return_in')
            then 'entrada'

        when movement_type in ('sale_out', 'return_out')
            then 'saida'

        else 'nao_classificado'
    end as movement_direction,

    abs(quantity) as absolute_quantity,

    reference_table,
    reference_id,
    employee_id,
    notes,

    case
        when lower(coalesce(notes, ''))
            like '%opening balance%system migration%'
            then true
        else false
    end as is_legacy_migration,

    occurred_at

from stock_movements