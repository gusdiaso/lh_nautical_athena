-- ============================================================
-- int_location_coordinates.sql
-- Grão:
-- uma linha por localização física real (loja ou armazém)
--
-- Cada unidade recebe a coordenada da capital da sua UF. Os nomes
-- de cidade de dim_locations são fictícios e não existem em base
-- oficial, então a UF é a única chave geográfica confiável. Duas
-- unidades na mesma UF ficam a distância zero uma da outra.
--
-- O join é LEFT de propósito: unidade com UF sem coordenada fica
-- com latitude nula e reprova o teste not_null deste modelo, em
-- vez de sumir em silêncio da análise. O membro técnico
-- (nk_location_id = -1) não tem UF e fica de fora.
-- ============================================================

with locations as (
    select
        sk_location
        , nk_location_id
        , location_name
        , location_type
        , city
        , state
        , region
        , is_active
    from {{ ref('dim_locations') }}
    where not is_technical_member
)

, final as (
    select
        locations.sk_location
        , locations.nk_location_id
        , locations.location_name
        , locations.location_type
        , locations.city
        , locations.state
        , locations.region
        , locations.is_active
        , coordinates.latitude
        , coordinates.longitude
    from locations
    left join {{ ref('int_uf_coordinates') }} as coordinates
        on upper(trim(locations.state)) = coordinates.state
)

select * from final
