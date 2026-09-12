{{ config(
    post_hook=mask_post_hooks({
        "tax_id": "mask_full",
        "email": "mask_email",
        "phone": "mask_phone",
    })
) }}

with source as (
    select
        supplier_id
        , legal_name
        , trade_name
        , country
        , tax_id
        , tax_id_type
        , email
        , contact_name
        , is_active
        , trim(phone) as phone
    from {{ ref('stg_suppliers') }}
)

, cleaned as (
    select
        supplier_id
        , legal_name
        , trade_name
        , country
        , tax_id
        , tax_id_type
        , contact_name
        , phone
        , email
        , is_active
        , trim(regexp_replace(phone, '^(55)?0?', '')) as digits
    from source
)

select
    supplier_id
    , legal_name
    , trade_name
    , country
    , tax_id
    , tax_id_type
    , email
    , contact_name
    , is_active
    , case
        when length(digits) >= 10
            then
                concat('55', substring(digits, 1, 2), '9', substring(digits, 3))
        else phone
    end as phone
from cleaned
