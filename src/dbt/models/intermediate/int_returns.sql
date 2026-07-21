with returns as (
    select
        return_id
        , return_number
        , order_id
        , customer_id
        , received_at_location_id
        , status
        , original_reason
        , reason_normalized
        , total_refund_amount
        , created_at
    from {{ ref('stg_returns') }}
)

, classified as (
    select
        return_id
        , return_number
        , order_id
        , customer_id
        , received_at_location_id
        , original_reason
        , reason_normalized
        , total_refund_amount
        , created_at
        , lower(trim(status)) as status
        , case
            when
                reason_normalized is null
                or trim(reason_normalized) in ('?', '-', '')
                then 'nao_informado'
            when reason_normalized like '%duplicada%'
                then 'compra_duplicada'
            when reason_normalized like '%desist%'
                then 'desistencia_cliente'
            when
                reason_normalized like '%descri%'
                or reason_normalized like '%corresponde%'
                or reason_normalized like '%corressponde%'
                then 'divergencia_descricao'
            when
                reason_normalized like '%avariado%'
                or reason_normalized like '%variado%'
                or reason_normalized like '%transporte%'
                then 'avaria_transporte'
            when reason_normalized like '%defeito%'
                then 'defeito_fabrica'
            when
                reason_normalized like '%tamanho%'
                or reason_normalized like '%cor%'
                then 'tamanho_cor_incorretos'
            when reason_normalized like '%outros%'
                then 'outros'
            else 'outros'
        end as return_reason_group
        , coalesce(total_refund_amount > 0, false) as has_refund_amount
    from returns
)

, final as (
    select
        return_id
        , return_number
        , order_id
        , customer_id
        , received_at_location_id
        , status
        , original_reason
        , reason_normalized
        , return_reason_group
        , total_refund_amount
        , has_refund_amount
        , created_at
    from classified
)

select * from final
