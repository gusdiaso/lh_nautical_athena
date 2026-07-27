with source as (
    select
        product_variant_id
        , location_id
        , quantity_on_hand
        , reorder_point
    from {{ ref('stg_stock_levels') }}
)

, rounded as (
    select
        product_variant_id
        , location_id
        , round(cast(quantity_on_hand as decimal(10,2)), 2) as quantity_on_hand
        , reorder_point
    from source
)

, demand as (
    select
        oi.product_variant_id
        , o.location_id
        , sum(oi.quantity_ordered) / 90.0 as avg_daily_demand
    from {{ ref('stg_order_items') }} oi
    inner join {{ ref('stg_orders') }} o
        on oi.order_id = o.order_id
    where lower(trim(o.status)) != 'cancelled'
      and cast(o.placed_at as date) >= date_add(current_date(), -90)
    group by oi.product_variant_id, o.location_id
)

, product_lead_times as (
    select
        product_variant_id
        , max(lead_time_days) as lead_time_days
    from {{ ref('int_product_suppliers') }}
    group by product_variant_id
)

, calculated as (
    select
        r.product_variant_id
        , r.location_id
        , r.quantity_on_hand
        , cast(
            coalesce(r.reorder_point,
                greatest(
                    coalesce(
                        ceil(
                            coalesce(d.avg_daily_demand, 0)
                            * coalesce(lt.lead_time_days, 7)
                        ),
                        0
                    ),
                    1
                )
            ) as decimal(10,2)
        ) as reorder_point
    from rounded r
    left join demand d
        on r.product_variant_id = d.product_variant_id
        and r.location_id = d.location_id
    left join product_lead_times lt
        on r.product_variant_id = lt.product_variant_id
)

, with_unit as (
    select
        c.product_variant_id
        , c.location_id
        , c.quantity_on_hand
        , c.reorder_point
        , p.unit_of_measure
    from calculated c
    left join {{ ref('stg_product_variants') }} pv
        on c.product_variant_id = pv.product_variant_id
    left join {{ ref('stg_products') }} p
        on pv.product_id = p.product_id
)

select
    product_variant_id
    , location_id
    , quantity_on_hand
    , reorder_point
    , coalesce(quantity_on_hand <= 0 or quantity_on_hand < reorder_point, false) as is_critical_stock
    , upper(trim(unit_of_measure)) in ('M', 'L')
        and quantity_on_hand != floor(quantity_on_hand)
        as is_fractional_item
from with_unit
