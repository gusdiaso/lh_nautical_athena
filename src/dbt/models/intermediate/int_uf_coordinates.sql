-- ============================================================
-- int_uf_coordinates.sql
-- Grão:
-- uma linha por UF (capital como ponto representativo)
--
-- Serve dois papéis na análise de expansão da rede: posição do
-- cliente médio de cada UF, para medir distância de atendimento,
-- e lista das 27 UFs candidatas a receber um novo ponto.
-- ============================================================

with coordinates as (
    select
        capital_city
        , cast(latitude as double) as latitude
        , cast(longitude as double) as longitude
        , upper(trim(uf)) as state
    from {{ ref('geo_uf_capital_coordinates') }}
)

select * from coordinates
