-- ============================================================
-- fact_stock_movements.sql
-- Grão:
-- uma linha por movimentação individual de estoque
--
-- A fato registra entradas e saídas de produtos por localização,
-- funcionário responsável e data da movimentação.
--
-- Movimentações sem funcionário são classificadas entre
-- migração de legado, sistema de e-commerce e não informado.
-- ============================================================

with stock_movements as (
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
        , movement_direction
        , absolute_quantity
        , is_legacy_migration
    from {{ ref('int_stock_movements') }}
)

, resolved_movements as (
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
        , movement_direction
        , absolute_quantity
        , is_legacy_migration
        , case
            when employee_id is not null
                then employee_id
            when is_legacy_migration
                then -1
            when
                movement_type = 'sale_out'
                and notes is null
                then -2
            else -3
        end as resolved_employee_id
    from stock_movements
)

, products as (
    select
        sk_product
        , nk_product_variant_id
    from {{ ref('dim_products') }}
)

, locations as (
    select
        sk_location
        , nk_location_id
    from {{ ref('dim_locations') }}
)

, employees as (
    select
        sk_employee
        , nk_employee_id
    from {{ ref('dim_employees') }}
)

, dates as (
    select
        sk_date
        , full_date
    from {{ ref('dim_date') }}
)

, joined as (
    select
        resolved_movements.stock_movement_id as nk_stock_movement_id
        , dates.sk_date
        , resolved_movements.reference_table
        , resolved_movements.reference_id as nk_reference_id
        , resolved_movements.movement_type
        , resolved_movements.movement_direction
        , resolved_movements.quantity
        , resolved_movements.absolute_quantity
        , resolved_movements.notes
        , resolved_movements.occurred_at
        , resolved_movements.is_legacy_migration
        , cast(1 as integer) as movement_count
        , md5(
            concat_ws(
                '||'
                , 'stock_movement'
                , cast(resolved_movements.stock_movement_id as string)
            )
        ) as sk_stock_movement
        , coalesce(
            products.sk_product
            , md5('product||nao_informado')
        ) as sk_product
        , coalesce(
            locations.sk_location
            , md5('location||nao_informada')
        ) as sk_location
        , coalesce(
            employees.sk_employee
            , md5('employee||nao_informado')
        ) as sk_employee
        , resolved_movements.movement_direction = 'entrada' as is_inbound
        , resolved_movements.movement_direction = 'saida' as is_outbound
    from resolved_movements
    left join products
        on
            resolved_movements.product_variant_id
            = products.nk_product_variant_id
    left join locations
        on
            resolved_movements.location_id
            = locations.nk_location_id
    left join employees
        on
            resolved_movements.resolved_employee_id
            = employees.nk_employee_id
    left join dates
        on
            cast(resolved_movements.occurred_at as date)
            = dates.full_date
)

, final as (
    select
        sk_stock_movement
        , nk_stock_movement_id
        , sk_product
        , sk_location
        , sk_employee
        , sk_date
        , reference_table
        , nk_reference_id
        , movement_type
        , movement_direction
        , quantity
        , absolute_quantity
        , notes
        , occurred_at
        , is_legacy_migration
        , is_inbound
        , is_outbound
        , movement_count
    from joined
)

select * from final
