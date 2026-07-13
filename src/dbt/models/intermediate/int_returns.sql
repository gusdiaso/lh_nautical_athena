with returns as (

    select *
    from {{ ref('stg_returns') }}

)

select
    return_id,
    return_number,
    order_id,
    customer_id,
    received_at_location_id,
    status,
    reason as original_reason,

    case
        when reason is null
            or trim(reason) in ('?', '—', '-')
            then 'nao_informado'

        when lower(trim(reason)) like '%duplicada%'
            then 'compra_duplicada'

        when lower(trim(reason)) like '%desist%'
            then 'desistencia_cliente'

        when lower(trim(reason)) like '%descri%'
            or lower(trim(reason)) like '%corresponde%'
            or lower(trim(reason)) like '%corressponde%'
            then 'divergencia_descricao'

        when lower(trim(reason)) like '%avariado%'
            or lower(trim(reason)) like '%variado%'
            or lower(trim(reason)) like '%transporte%'
            then 'avaria_transporte'

        when lower(trim(reason)) like '%defeito%'
            then 'defeito_fabrica'

        when lower(trim(reason)) like '%tamanho%'
            or lower(trim(reason)) like '%cor%'
            then 'tamanho_cor_incorretos'

        when lower(trim(reason)) like '%outros%'
            then 'outros'

        else 'outros'
    end as return_reason_group,

    total_refund_amount,

    case
        when total_refund_amount > 0 then true
        else false
    end as has_refund_amount,

    created_at,
    updated_at


from returns