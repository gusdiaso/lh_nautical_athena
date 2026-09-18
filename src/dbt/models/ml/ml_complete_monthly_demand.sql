-- ============================================================
-- ml_complete_monthly_demand.sql
-- Grão:
-- uma linha por produto (SKU) × loja × mês (primeiro dia do mês)
--
-- Base compartilhada da engenharia de features de Machine Learning
-- (Etapa 3 do plano de previsão, notebooks 01-03 em notebooks/ml).
-- Remove os meses parciais de agg_demand_monthly antes de qualquer
-- janela móvel: o primeiro mês de cada combinação produto × loja
-- (começa no dia da primeira venda, nunca é um mês cheio) e o
-- último mês do dataset (pode estar pela metade). Os dois
-- distorceriam MM12/MM3, o índice sazonal e a tendência se
-- entrassem nas contas — mesmo critério usado nos notebooks 01-03
-- (add_partial_period_flag / complete_months em
-- src/analytics_ai/eda_demand_zeros.py e eda_demand_distribution.py).
--
-- days_in_period < dias do calendário no mês ⇒ mês parcial.
-- ============================================================

with monthly as (
    select
        sk_product
        , sk_location
        , month_start_date
        , days_in_period
        , demand_quantity
    from {{ ref('agg_demand_monthly') }}
)

, final as (
    select
        sk_product
        , sk_location
        , month_start_date
        , demand_quantity
    from monthly
    where days_in_period >= dayofmonth(last_day(month_start_date))
)

select * from final
