-- stg_suppliers.sql

with source as (

    select *
    from {{ source('bronze', 'suppliers') }}

)

select
    id as supplier_id
    , legal_name
    , trade_name
    , country
    , tax_id
    , tax_id_type
    , email
    , phone
    , contact_name
    , is_active
from source
