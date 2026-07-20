-- ============================================================
-- dim_date.sql
-- Grão:
-- uma linha por dia do calendário
--
-- O intervalo considera a menor e a maior data presentes
-- nos processos operacionais disponíveis no projeto.
--
-- A data final recebe uma margem de um ano para permitir
-- análises futuras e acompanhar a evolução dos dados.
--
-- Inclui atributos de calendário e indicadores auxiliares
-- para análises temporais.
-- ============================================================

with event_dates as (
    select
        cast(placed_at as date) as event_date
    from {{ ref('int_orders') }}
    where placed_at is not null

    union all

    select
        cast(occurred_at as date) as event_date
    from {{ ref('int_stock_movements') }}
    where occurred_at is not null

    union all

    select
        cast(paid_at as date) as event_date
    from {{ ref('int_payments') }}
    where paid_at is not null

    union all

    select
        cast(placed_at as date) as event_date
    from {{ ref('int_purchase_orders') }}
    where placed_at is not null

    union all

    select
        cast(expected_delivery_at as date) as event_date
    from {{ ref('int_purchase_orders') }}
    where expected_delivery_at is not null

    union all

    select
        cast(received_at as date) as event_date
    from {{ ref('int_goods_receipts') }}
    where received_at is not null

    union all

    select
        cast(exchange_date as date) as event_date
    from {{ ref('int_exchange_rates') }}
    where exchange_date is not null
)

, date_bounds as (
    select
        min(event_date) as start_date
        , date_add(max(event_date), 365) as end_date
    from event_dates
)

, date_spine as (
    select
        explode(
            sequence(
                start_date
                , end_date
                , interval 1 day
            )
        ) as date_day
    from date_bounds
)

, dates as (
    select
        cast(date_format(date_day, 'yyyyMMdd') as int) as sk_date
        , cast(date_day as date) as full_date
        , day(date_day) as day_number
        , dayofyear(date_day) as day_of_year
        , year(date_day) as year_number
        , month(date_day) as month_number
        , quarter(date_day) as quarter_number
        , weekofyear(date_day) as week_of_year
        , pmod(dayofweek(date_day) + 5, 7) + 1 as day_of_week_number
        , case
            when pmod(dayofweek(date_day) + 5, 7) + 1 = 1
                then 'Segunda-feira'
            when pmod(dayofweek(date_day) + 5, 7) + 1 = 2
                then 'Terça-feira'
            when pmod(dayofweek(date_day) + 5, 7) + 1 = 3
                then 'Quarta-feira'
            when pmod(dayofweek(date_day) + 5, 7) + 1 = 4
                then 'Quinta-feira'
            when pmod(dayofweek(date_day) + 5, 7) + 1 = 5
                then 'Sexta-feira'
            when pmod(dayofweek(date_day) + 5, 7) + 1 = 6
                then 'Sábado'
            when pmod(dayofweek(date_day) + 5, 7) + 1 = 7
                then 'Domingo'
        end as day_of_week_name
        , case
            when month(date_day) = 1 then 'Janeiro'
            when month(date_day) = 2 then 'Fevereiro'
            when month(date_day) = 3 then 'Março'
            when month(date_day) = 4 then 'Abril'
            when month(date_day) = 5 then 'Maio'
            when month(date_day) = 6 then 'Junho'
            when month(date_day) = 7 then 'Julho'
            when month(date_day) = 8 then 'Agosto'
            when month(date_day) = 9 then 'Setembro'
            when month(date_day) = 10 then 'Outubro'
            when month(date_day) = 11 then 'Novembro'
            when month(date_day) = 12 then 'Dezembro'
        end as month_name
        , concat(
            cast(year(date_day) as string)
            , '-'
            , lpad(cast(month(date_day) as string), 2, '0')
        ) as year_month
        , concat(
            'T'
            , cast(quarter(date_day) as string)
        ) as quarter_name
        , concat(
            cast(year(date_day) as string)
            , '-T'
            , cast(quarter(date_day) as string)
        ) as year_quarter
        , case
            when month(date_day) <= 6 then 1
            else 2
        end as semester_number
        , pmod(dayofweek(date_day) + 5, 7) + 1 in (6, 7) as is_weekend
        , month(date_day) in (10, 11, 12, 1) as is_high_season
    from date_spine
)

, final as (
    select
        sk_date
        , full_date
        , day_number
        , day_of_year
        , day_of_week_number
        , day_of_week_name
        , week_of_year
        , month_number
        , month_name
        , year_month
        , quarter_number
        , quarter_name
        , year_quarter
        , semester_number
        , year_number
        , is_weekend
        , is_high_season
    from dates
)

select * from final;