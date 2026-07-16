-- stg_attributes.sql

with source as (

    select *
    from {{ source('bronze', 'attributes') }}

)

select
    cast(id as integer) as attribute_id
    , name as attribute_name
    , data_type

from source
