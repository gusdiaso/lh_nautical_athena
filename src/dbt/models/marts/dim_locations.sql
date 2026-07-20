-- ============================================================
-- dim_locations.sql
-- Grão:
-- uma linha por localização física
-- + membro técnico para localização não informada
-- ============================================================

with locations as (
    select
        location_id
        , location_name
        , location_type
        , postal_code
        , street
        , number
        , complement
        , district
        , city
        , state
        , country
        , is_active
    from {{ ref('int_locations') }}
)

, technical_location as (
    select
        md5('location||nao_informada') as sk_location
        , cast(-1 as bigint) as nk_location_id
        , 'Localização não informada' as location_name
        , 'nao_informado' as location_type
        , cast(null as string) as postal_code
        , cast(null as string) as street
        , cast(null as string) as number
        , cast(null as string) as complement
        , cast(null as string) as district
        , cast(null as string) as city
        , cast(null as string) as state
        , cast(null as string) as country
        , false as is_active
        , true as is_technical_member
)

, locations_dimension as (
    select
        md5(
            concat_ws(
                '||'
                , 'location'
                , cast(location_id as string)
            )
        ) as sk_location
        , location_id as nk_location_id
        , location_name
        , location_type
        , postal_code
        , street
        , number
        , complement
        , district
        , city
        , state
        , country
        , is_active
        , false as is_technical_member
    from locations
)

, final as (
    select
        sk_location
        , nk_location_id
        , location_name
        , location_type
        , postal_code
        , street
        , number
        , complement
        , district
        , city
        , state
        , country
        , is_active
        , is_technical_member
    from technical_location

    union all

    select
        sk_location
        , nk_location_id
        , location_name
        , location_type
        , postal_code
        , street
        , number
        , complement
        , district
        , city
        , state
        , country
        , is_active
        , is_technical_member
    from locations_dimension
)

select * from final