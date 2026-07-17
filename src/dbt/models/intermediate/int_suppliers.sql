with source as (
    select
        supplier_id
        , legal_name
        , trade_name
        , country
        , tax_id
        , tax_id_type
        , email
        , phone
        , contact_name
        , is_active
    from {{ ref('stg_suppliers') }}
)

, final as (
    select
        supplier_id
        , trim(legal_name) as legal_name
        , trim(trade_name) as trade_name
        , country
        , tax_id
        , tax_id_type
        , email
        , phone
        , trim(contact_name) as contact_name
        , is_active
    from source
)

select * from final