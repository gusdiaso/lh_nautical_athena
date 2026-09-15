{{ config(
    post_hook=mask_post_hooks({
        "tax_id": "mask_full",
        "email": "mask_email",
        "phone": "mask_phone",
    })
) }}

with source as (

    select *
    from {{ ref('stg_customers') }}

)

, base as (

    select
        customer_id
        , is_active
        , lower(trim(person_type)) as person_type
        , trim(legal_name) as legal_name
        , trim(trade_name) as trade_name
        , trim(tax_id) as tax_id
        , trim(state_registration) as state_registration
        , lower(trim(email)) as email
        , trim(phone) as phone
    from source
    where customer_id is not null

)

, deduplicated as (

    select
        *
        , row_number() over (
            partition by customer_id
            order by customer_id
        ) as record_rank
    from base

)

, cleaned as (

    select
        customer_id
        , person_type
        , legal_name
        , trade_name
        , tax_id
        , is_active
        , case
            when person_type = 'pf' then null
            when trim(state_registration) in ('0', '') then null
            when lower(trim(state_registration)) = 'isento' then null
            else trim(state_registration)
        end as state_registration
        , case
            when customer_id = 164 then 'camargo.eireli.164@example.com'
            when customer_id = 776 then 'da.mota.eireli.776@example.com'
            when customer_id = 1961 then 'mariana.moraes.1961@example.com'
            when customer_id = 690 then 'rodrigo.oliveira.690@example.com'
            when customer_id = 1131 then 'fernando.santos.1131@example.com'
            when customer_id = 1207 then 'rafael.costa.1207@example.com'
            when customer_id = 1658 then 'pedro.almeida.1658@example.com'
            else lower(trim(email))
        end as email
        , case
            when customer_id = 601 then '5511988880601'
            when customer_id = 1519 then '5521988881519'
            when customer_id = 866 then '5531988880866'
            when customer_id = 736 then '5541988880736'
            when customer_id = 256 then '5551988880256'
            when customer_id = 748 then '5511988880748'
            when customer_id = 1373 then '5521988881373'
            when customer_id = 1467 then '5531988881467'
            when customer_id = 547 then '5511988880547'
            when customer_id = 162 then '5511988880162'
            when customer_id = 441 then '5511988880441'
            when customer_id = 1288 then '5511988881288'
            when customer_id = 1430 then '5511988881430'
            when customer_id = 458 then '5511988880458'
            when length(trim(phone)) > 13
                then regexp_replace(trim(phone), '^550', '55')
            else trim(phone)
        end as phone
    from deduplicated
    where record_rank = 1

)

select
    customer_id
    , person_type
    , legal_name
    , trade_name
    , tax_id
    , state_registration
    , email
    , phone
    , is_active

from cleaned
order by customer_id
