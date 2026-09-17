-- ============================================================
-- agg_demand_weekly.sql
-- Grão:
-- uma linha por produto (SKU) × loja × semana (início na
-- segunda-feira)
--
-- Agrega agg_demand_daily em blocos semanais — mesma fonte,
-- mesma definição de demanda (P2), mesmo preenchimento de zeros
-- já resolvido na camada diária. Isso garante que a comparação
-- de granularidade (P1 do plano de ML) seja justa: as duas
-- séries vêm exatamente da mesma lógica, só muda o agrupamento.
--
-- week_start_date vem de date_trunc('week', full_date), não da
-- combinação week_of_year + year_number de dim_date: nessa
-- combinação, a virada do ano quebra o agrupamento (uma semana
-- pode ter dias de dezembro classificados no week_of_year da
-- semana ISO seguinte, com year_number ainda do ano civil
-- anterior) e juntaria ou separaria semanas erradas. Truncar a
-- data diretamente evita esse bug de fronteira de ano.
--
-- Por herdar o preenchimento de zeros de agg_demand_daily, esta
-- tabela já nasce densa: toda semana dentro da janela de
-- atividade de cada combinação aparece, mesmo sem venda.
--
-- days_in_period conta quantos dias da série diária caíram na
-- semana — menor que 7 na semana da primeira venda da combinação
-- e na última semana do dataset, se o corte cair no meio dela.
-- Mesma coluna de agg_demand_monthly/quarterly, para filtrar
-- períodos parciais do mesmo jeito nos três grãos agregados.
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
        , cast(date_trunc('week', full_date) as date) as week_start_date
        , count(*) as days_in_period
        , sum(demand_quantity) as demand_quantity
    from daily
    group by
        sk_product
        , sk_location
        , cast(date_trunc('week', full_date) as date)
)

select * from final
