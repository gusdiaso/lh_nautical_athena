-- ============================================================
-- agg_demand_quarterly.sql
-- Grão:
-- uma linha por produto (SKU) × loja × trimestre (primeiro dia
-- do trimestre)
--
-- Agrega agg_demand_daily em blocos trimestrais — mesma fonte,
-- mesma definição de demanda (P2), mesmo preenchimento de zeros
-- já resolvido na camada diária. Com agg_demand_weekly e
-- agg_demand_monthly, completa a comparação de granularidade
-- (P1 do plano de ML): as quatro séries vêm exatamente da mesma
-- lógica, só muda o agrupamento.
--
-- O grão trimestral coincide com o horizonte de 3 meses do
-- plano: um passo à frente já é o total do trimestre. Em troca,
-- a série fica curta (quatro pontos por ano) e não mostra como
-- a demanda se distribui dentro do trimestre.
--
-- Os trimestres são de calendário (jan–mar, abr–jun, jul–set,
-- out–dez), via date_trunc('quarter', full_date). A alta
-- temporada náutica (novembro a abril com os dados atuais, ver
-- int_high_season_months) atravessa três trimestres: out–dez pega
-- dois meses dela, jan–mar os três e abr–jun só abril.
--
-- days_in_period conta quantos dias da série diária caíram no
-- trimestre. Fica abaixo dos dias do calendário no trimestre da
-- primeira venda da combinação e no último trimestre do dataset,
-- se o corte final cair no meio dele. Os dois distorcem a série
-- em sentidos opostos (o primeiro sempre tem venda, o último
-- soma menos dias) e precisam ser tratados antes de treinar ou
-- avaliar um modelo.
-- ============================================================

with daily as (
    select
        sk_product
        , sk_location
        , full_date
        , demand_quantity
    from {{ ref('agg_demand_daily') }}
)

, final as (
    select
        sk_product
        , sk_location
        , cast(date_trunc('quarter', full_date) as date) as quarter_start_date
        , count(*) as days_in_period
        , sum(demand_quantity) as demand_quantity
    from daily
    group by
        sk_product
        , sk_location
        , cast(date_trunc('quarter', full_date) as date)
)

select * from final
