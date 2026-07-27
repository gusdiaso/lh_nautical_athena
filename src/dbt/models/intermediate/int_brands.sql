with source as (

    select *
    from {{ ref('stg_brands') }}

)

, base as (

    select
        brand_id
        , is_active
        , trim(brand_name) as brand_name
        , case trim(brand_name)
            when 'Yamaha Marine' then 'JP'
            when 'Mercury Marine' then 'US'
            when 'Suzuki Marine' then 'JP'
            when 'Honda Marine' then 'JP'
            when 'Garmin' then 'US'
            when 'Raymarine' then 'GB'
            when 'Lowrance' then 'US'
            when 'Simrad' then 'NO'
            when 'Volvo Penta' then 'SE'
            when 'MaxSea' then 'FR'
            when 'BR Náutica' then 'BR'
            when 'Marisul' then 'BR'
            else upper(trim(country))
        end as country
    from source
    where brand_id is not null

)

, deduplicated as (

    select
        *
        , row_number() over (
            partition by brand_id
            order by brand_id
        ) as record_rank
    from base

)

select
    brand_id
    , brand_name
    , country
    , is_active

from deduplicated
where record_rank = 1
