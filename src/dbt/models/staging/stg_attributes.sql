-- stg_attributes.sql

with source as (

    select *
    from {{ source('bronze', 'attributes') }}

)

select
    id as attribute_id
    , name as attribute_name
    , data_type

from source
