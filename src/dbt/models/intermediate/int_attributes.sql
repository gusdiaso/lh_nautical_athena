with source as (

    select *
    from {{ ref('stg_attributes') }}

)

, base as (

    select
        attribute_id
        , trim(attribute_name) as attribute_name
        , lower(trim(data_type)) as data_type
    from source
    where attribute_id is not null

)

, deduplicated as (

    select
        *
        , row_number() over (
            partition by attribute_id
            order by attribute_id
        ) as record_rank
    from base

)

select
    attribute_id
    , attribute_name
    , data_type

from deduplicated
where record_rank = 1
