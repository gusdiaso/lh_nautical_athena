-- ============================================================
-- ml_seasonal_trend.sql
-- Grão:
-- uma linha por mês de corte (mês completo, primeiro dia do mês)
--
-- Índice sazonal e fator de tendência recalculados EM CADA CORTE,
-- só com meses até o próprio corte — porta para SQL o que os
-- notebooks 01-03 fazem em pandas (seasonal_index_at / trend_factor_at
-- em src/analytics_ai/demand_baselines.py), agora para todo corte
-- possível do histórico, não só os 12 de teste + 24 de calibração
-- usados na avaliação do notebook 03. É o ingrediente de
-- estação/tendência da tabela final de features (ml_features_produto_loja_mes).
--
-- Índice sazonal (mesma regra de int_high_season_months, mas ponto
-- no tempo): para cada mês do ano (1-12), a média da demanda total
-- (todas as séries somadas) desse mês do ano até o corte, dividida
-- pela média das 12 médias mensais até o corte. Só fica pronto
-- (seasonal_ready = true) quando os 12 meses do ano já apareceram
-- ao menos uma vez no histórico até o corte — sem isso a média geral
-- (denominador) não é confiável.
--
-- Atalho usado em vez de um "as of join": a ocorrência mais recente
-- do mês-número X até um corte C é sempre no ano de C (se X <= mês
-- de C) ou no ano anterior (se X > mês de C) — nunca ambígua —, então
-- a data-âncora de cada mês-número é calculada direto (anchor_date),
-- sem procurar a linha mais próxima.
--
-- season_sum_next_3m é o ingrediente sazonal das réguas do notebook
-- 03 (MM12 × soma dos índices dos 3 meses previstos).
--
-- Fator de tendência: crescimento dos 12 meses até o corte sobre os
-- 12 anteriores, elevado a 7,5/12 — a distância, em meses, entre o
-- centro da janela da MM12 (5,5 meses antes do corte) e o centro
-- dos 3 meses previstos (2 meses depois do corte). Mesma constante
-- MM12_LAG_MONTHS do notebook 03. trend_ready = false (e
-- growth_12m/trend_factor nulos) nos cortes que ainda não têm 24
-- meses de histórico.
-- ============================================================

with totals as (
    select
        month_start_date
        , sum(demand_quantity) as demand_quantity
    from {{ ref('ml_complete_monthly_demand') }}
    group by month_start_date
)

, running_by_month_number as (
    select
        month_start_date
        , month(month_start_date) as month_number
        , avg(demand_quantity) over (
            partition by month(month_start_date)
            order by month_start_date
            rows between unbounded preceding and current row
        ) as running_avg_demand
    from totals
)

, month_numbers as (
    select explode(sequence(1, 12)) as month_number
)

, month_number_grid as (
    select
        totals.month_start_date as cutoff
        , grid.month_number
    from totals
    cross join month_numbers as grid
)

, anchored as (
    select
        month_number_grid.cutoff
        , month_number_grid.month_number
        , make_date(
            year(month_number_grid.cutoff)
            - case when month_number_grid.month_number > month(month_number_grid.cutoff) then 1 else 0 end
            , month_number_grid.month_number
            , 1
        ) as anchor_date
    from month_number_grid
)

, seasonal_by_month_number as (
    select
        anchored.cutoff
        , anchored.month_number
        , running_by_month_number.running_avg_demand
    from anchored
    left join running_by_month_number
        on
            anchored.anchor_date = running_by_month_number.month_start_date
            and anchored.month_number = running_by_month_number.month_number
)

, seasonal_index as (
    select
        cutoff
        , month_number
        , count(running_avg_demand) over (partition by cutoff) as month_numbers_with_history
        , running_avg_demand / avg(running_avg_demand) over (partition by cutoff) as seasonal_index
    from seasonal_by_month_number
)

, next_three_offsets as (
    select explode(sequence(1, 3)) as months_ahead
)

, next_3_months as (
    select
        totals.month_start_date as cutoff
        , offsets.months_ahead
        , month(add_months(totals.month_start_date, offsets.months_ahead)) as target_month_number
    from totals
    cross join next_three_offsets as offsets
)

, season_sum as (
    select
        next_3_months.cutoff
        , max(seasonal_index.month_numbers_with_history) as month_numbers_with_history
        , sum(seasonal_index.seasonal_index) as season_sum_next_3m
        , max(
            case when next_3_months.months_ahead = 1 then seasonal_index.seasonal_index end
        ) as seasonal_index_month_plus1
        , max(
            case when next_3_months.months_ahead = 2 then seasonal_index.seasonal_index end
        ) as seasonal_index_month_plus2
        , max(
            case when next_3_months.months_ahead = 3 then seasonal_index.seasonal_index end
        ) as seasonal_index_month_plus3
    from next_3_months
    inner join seasonal_index
        on
            next_3_months.cutoff = seasonal_index.cutoff
            and next_3_months.target_month_number = seasonal_index.month_number
    group by next_3_months.cutoff
)

, trend as (
    select
        month_start_date as cutoff
        , sum(demand_quantity) over (
            order by month_start_date
            rows between 11 preceding and current row
        ) as demand_last_12m
        , sum(demand_quantity) over (
            order by month_start_date
            rows between 23 preceding and 12 preceding
        ) as demand_prev_12m
        , count(*) over (
            order by month_start_date
            rows between 23 preceding and current row
        ) as months_counted_24m
    from totals
)

, final as (
    select
        season_sum.cutoff
        , season_sum.seasonal_index_month_plus1
        , season_sum.seasonal_index_month_plus2
        , season_sum.seasonal_index_month_plus3
        , season_sum.season_sum_next_3m
        , season_sum.month_numbers_with_history = 12 as seasonal_ready
        , trend.months_counted_24m = 24 as trend_ready
        , case
            when trend.months_counted_24m = 24
                then trend.demand_last_12m / trend.demand_prev_12m
        end as growth_12m
        , case
            when trend.months_counted_24m = 24
                then power(trend.demand_last_12m / trend.demand_prev_12m, 7.5 / 12)
        end as trend_factor
    from season_sum
    inner join trend
        on season_sum.cutoff = trend.cutoff
)

select * from final
where seasonal_ready
