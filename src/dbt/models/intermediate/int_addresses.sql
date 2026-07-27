with source as (
    select
        address_id
        , customer_id
        , address_type
        , {{ clean_cep('postal_code') }} as postal_code
        , street
        , number
        , complement
        , district
        , city
        , state
        , country
        , is_primary
    from {{ ref('stg_addresses') }}
)

, final as (
    select
        address_id
        , customer_id
        , address_type
        , is_primary
        , postal_code
        , trim(street) as street
        , trim(number) as number
        , case
            when trim(complement) in ('?', '-', '—') then null
            else trim(complement)
        end as complement
        , trim(district) as district
        , trim(city) as city
        , trim(state) as state
        , trim(country) as country
    from source
)

select * from final
