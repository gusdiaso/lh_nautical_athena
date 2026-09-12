-- ============================================================
-- dim_suppliers.sql
-- Grão:
-- uma linha por fornecedor cadastrado
-- + membro técnico para fornecedor não informado
--
-- Esta dimensão centraliza os atributos cadastrais utilizados
-- nas análises de compras, abastecimento e SLA de fornecedores.
-- ============================================================

{{ config(
    post_hook=mask_post_hooks({
        "tax_id": "mask_full",
        "email": "mask_email",
        "phone": "mask_phone",
    })
) }}

with suppliers as (
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
    from {{ ref('int_suppliers') }}
)

, technical_supplier as (
    select
        cast(-1 as bigint) as nk_supplier_id
        , 'Fornecedor não informado' as legal_name
        , cast(null as string) as trade_name
        , cast(null as string) as country
        , cast(null as string) as tax_id
        , cast(null as string) as tax_id_type
        , cast(null as string) as email
        , cast(null as string) as phone
        , cast(null as string) as contact_name
        , false as is_active
        , true as is_technical_member
        , md5('supplier||nao_informado') as sk_supplier
)

, suppliers_dimension as (
    select
        supplier_id as nk_supplier_id
        , legal_name
        , trade_name
        , country
        , tax_id
        , tax_id_type
        , email
        , phone
        , contact_name
        , is_active
        , false as is_technical_member
        , {{ sk_from_keys(["'supplier'", 'supplier_id']) }} as sk_supplier
    from suppliers
)

, final as (
    select
        sk_supplier
        , nk_supplier_id
        , legal_name
        , trade_name
        , country
        , tax_id
        , tax_id_type
        , email
        , phone
        , contact_name
        , is_active
        , is_technical_member
    from technical_supplier

    union all

    select
        sk_supplier
        , nk_supplier_id
        , legal_name
        , trade_name
        , country
        , tax_id
        , tax_id_type
        , email
        , phone
        , contact_name
        , is_active
        , is_technical_member
    from suppliers_dimension
)

select * from final
