-- stg_stock_movements.sql

with source as (

    select *
    from {{ source('bronze', 'stock_movements') }}

)

select
    id as stock_movement_id,
    product_variant_id,
    location_id,
    movement_type,
    quantity,
    reference_table,
    reference_id,
    employee_id,
    trim(notes) as notes,
    occurred_at,
    created_at

from source