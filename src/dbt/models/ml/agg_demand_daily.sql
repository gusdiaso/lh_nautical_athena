-- ============================================================
-- agg_demand_daily.sql
-- Grão:
-- uma linha por produto (SKU) × loja × dia
--
-- Fundação de dados da Frente 1 do Plano de Modelagem Preditiva
-- (Checkpoint 05): a série de demanda que alimenta baselines
-- (D1), engenharia de features (D3) e os modelos de regressão
-- (D2). Só entra aqui a definição de demanda já decidida em P2
-- do plano — não se recalcula esse critério em nenhum outro
-- lugar do pipeline de ML.
--
-- Preenchimento de zeros (risco de série com buracos):
-- baseline de média móvel e lags precisam de uma linha do tempo
-- contínua — um dia sem venda tem que aparecer como quantidade
-- zero, não como ausência de linha, senão uma "SMA-4" real vira
-- uma média de dias não-consecutivos sem ninguém perceber.
-- Por isso cada combinação produto×loja é expandida do seu
-- primeiro dia de atividade até o último dia de atividade
-- observado em todo o dataset (mesmo corte final para todas as
-- combinações, para comparar períodos de teste iguais depois).
--
-- Não se preenche com zero ANTES da primeira venda da
-- combinação: isso inventaria demanda zero para um produto que
-- ainda nem estava à venda naquela loja, distorcendo qualquer
-- baseline ou lag calculado sobre esse trecho.
--
-- Combinações resolvidas para o membro técnico "não informado"
-- de produto/localização são excluídas — não faz sentido prever
-- demanda de um produto ou loja que não foi identificado.
--
-- Engenharia de features (lags, calendário, horizonte) e o
-- risco de vazamento de dados associado a ela ficam fora desta
-- tabela de propósito — isso é decisão de D3, ainda em aberto no
-- plano, e não deve ser antecipado aqui.
--
-- Materializada como table: é recalculada sob demanda pelo job
-- de forecast, não a cada consulta, e evita reprocessar a
-- expansão de calendário em toda leitura. O prefixo agg_ marca
-- que é uma agregação (soma de quantity_ordered), não um fato
-- transacional nem uma dimensão do star schema em gold.
-- ============================================================

with order_items as (
    select
        sk_product
        , sk_location
        , sk_date
        , quantity_ordered
    from {{ ref('fact_order_items') }}
    where is_confirmed or is_paid
)

, dates as (
    select
        sk_date
        , full_date
    from {{ ref('dim_date') }}
)

, products as (
    select sk_product
    from {{ ref('dim_products') }}
    where not is_technical_member
)

, locations as (
    select sk_location
    from {{ ref('dim_locations') }}
    where not is_technical_member
)

, daily_sales as (
    select
        order_items.sk_product
        , order_items.sk_location
        , dates.full_date
        , sum(order_items.quantity_ordered) as demand_quantity
    from order_items
    inner join dates
        on order_items.sk_date = dates.sk_date
    inner join products
        on order_items.sk_product = products.sk_product
    inner join locations
        on order_items.sk_location = locations.sk_location
    group by
        order_items.sk_product
        , order_items.sk_location
        , dates.full_date
)

, combination_bounds as (
    select
        sk_product
        , sk_location
        , min(full_date) as first_active_date
    from daily_sales
    group by
        sk_product
        , sk_location
)

, global_bounds as (
    select max(full_date) as last_active_date
    from daily_sales
)

, date_spine as (
    select
        combination_bounds.sk_product
        , combination_bounds.sk_location
        , explode(
            sequence(
                combination_bounds.first_active_date
                , global_bounds.last_active_date
                , interval 1 day
            )
        ) as full_date
    from combination_bounds
    cross join global_bounds
)

, final as (
    select
        date_spine.sk_product
        , date_spine.sk_location
        , date_spine.full_date
        , coalesce(daily_sales.demand_quantity, 0) as demand_quantity
    from date_spine
    left join daily_sales
        on
            date_spine.sk_product = daily_sales.sk_product
            and date_spine.sk_location = daily_sales.sk_location
            and date_spine.full_date = daily_sales.full_date
)

select * from final
