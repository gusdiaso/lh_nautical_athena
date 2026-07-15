select
    stock_movement_id
    , movement_type
    , quantity
    , movement_direction
    , absolute_quantity
    , is_legacy_migration
    , notes
from {{ ref('int_stock_movements') }}
where
    absolute_quantity <> abs(quantity)

    or (
        movement_type in ('purchase_in', 'return_in')
        and movement_direction <> 'entrada'
    )

    or (
        movement_type in ('sale_out', 'return_out')
        and movement_direction <> 'saida'
    )

    or (
        movement_direction = 'entrada'
        and quantity <= 0
    )

    or (
        movement_direction = 'saida'
        and quantity >= 0
    )

    or (
        lower(coalesce(notes, ''))
        like '%opening balance%system migration%'
        and is_legacy_migration = false
    )
