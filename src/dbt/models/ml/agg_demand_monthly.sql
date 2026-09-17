-- ============================================================
-- agg_demand_monthly.sql
-- Grão:
-- uma linha por produto (SKU) × loja × mês (primeiro dia do mês)
--
-- Agrega agg_demand_daily em blocos mensais — mesma fonte,
-- mesma definição de demanda (P2), mesmo preenchimento de zeros
-- já resolvido na camada diária. Com agg_demand_weekly, completa
-- a comparação de granularidade (P1 do plano de ML): as três
-- séries vêm exatamente da mesma lógica, só muda o agrupamento.
--
-- O grão mensal atende o horizonte de 3 meses do plano: prever
-- mês 1, mês 2 e mês 3 separadamente e somar dá o total do
-- trimestre sem perder a distribuição da demanda ao longo dele.
--
-- month_start_date vem de date_trunc('month', full_date) —
-- mesma lógica de truncar a data usada no semanal, sem depender
-- de combinações month_number + year_number de dim_date.
--
-- days_in_period conta quantos dias da série diária caíram no
-- mês. Fica abaixo do número de dias do calendário em dois
-- casos: o mês da primeira venda da combinação (a série diária
-- não é preenchida antes dela) e o último mês do dataset, se o
-- corte final cair no meio do mês. Os dois distorcem a série em
-- sentidos opostos: o primeiro mês sempre tem venda (a série
-- começa justamente nela) e o último soma menos dias que um mês
-- cheio. Precisam ser tratados (filtro ou normalização) antes de
-- treinar ou avaliar um modelo.
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
        , cast(date_trunc('month', full_date) as date) as month_start_date
        , count(*) as days_in_period
        , sum(demand_quantity) as demand_quantity
    from daily
    group by
        sk_product
        , sk_location
        , cast(date_trunc('month', full_date) as date)
)

select * from final
