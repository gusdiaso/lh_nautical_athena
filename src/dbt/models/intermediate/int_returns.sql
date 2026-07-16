with returns as (

    select *
    from {{ ref('stg_returns') }}

)

select
    return_id
    , return_number
    , order_id
    , customer_id
    , received_at_location_id
    , status
    , reason_normalized
    , total_refund_amount
    , case
        when
            reason_normalized is null
            or trim(reason_normalized) in ('?', '—', '-')
            then 'nao_informado'

        when lower(trim(reason_normalized)) like '%duplicada%'
            then 'compra_duplicada'

        when lower(trim(reason_normalized)) like '%desist%'
            then 'desistencia_cliente'

        when
            lower(trim(reason_normalized)) like '%descri%'
            or lower(trim(reason_normalized)) like '%corresponde%'
            or lower(trim(reason_normalized)) like '%corressponde%'
            then 'divergencia_descricao'

        when
            lower(trim(reason_normalized)) like '%avariado%'
            or lower(trim(reason_normalized)) like '%variado%'
            or lower(trim(reason_normalized)) like '%transporte%'
            then 'avaria_transporte'

        when lower(trim(reason_normalized)) like '%defeito%'
            then 'defeito_fabrica'

        when
            lower(trim(reason_normalized)) like '%tamanho%'
            or lower(trim(reason_normalized)) like '%cor%'
            then 'tamanho_cor_incorretos'

        when lower(trim(reason_normalized)) like '%outros%'
            then 'outros'

        else 'outros'
    end as return_reason_group
    , coalesce(total_refund_amount > 0, false) as has_refund_amount

from returns
