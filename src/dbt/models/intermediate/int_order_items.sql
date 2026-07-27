with source as (

    select *
    from {{ ref('stg_order_items') }}

)

, base as (

    select
        order_item_id
        , order_id
        , product_variant_id
        , quantity_ordered
        , unit_price
        , icms_rate
        , ipi_rate
        , original_line_total
    from source
    where order_item_id is not null

)

, deduplicated as (

    select
        *
        , row_number() over (
            partition by order_item_id
            order by order_item_id
        ) as record_rank
    from base

)

select
    order_item_id
    , order_id
    , product_variant_id
    , quantity_ordered
    , unit_price
    , icms_rate
    , ipi_rate
    , original_line_total
    , round(
        original_line_total * icms_rate / 100
        , 2
    ) as icms_amount
    , round(
        original_line_total * ipi_rate / 100
        , 2
    ) as ipi_amount
    , round(
        original_line_total * (icms_rate + ipi_rate) / 100
        , 2
    ) as total_tax_amount
    , round(
        original_line_total * (1 + (icms_rate + ipi_rate) / 100)
        , 2
    ) as total_with_taxes

from deduplicated
where record_rank = 1
