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
        , country
        , tax_id
        , tax_id_type
        , email
        , phone
        , is_active
        , trim(legal_name) as legal_name
        , trim(trade_name) as trade_name
        , trim(contact_name) as contact_name
    from source
)

select * from final
