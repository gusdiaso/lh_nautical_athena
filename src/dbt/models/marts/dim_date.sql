with candidate_dates as (

    select cast(placed_at as date) as event_date
    from {{ ref('int_orders') }}
    where placed_at is not null

    union all

    select cast(paid_at as date) as event_date
    from {{ ref('int_payments') }}
    where paid_at is not null

    union all

    select cast(received_at as date) as event_date
    from {{ ref('int_goods_receipts') }}
    where received_at is not null

    union all

    select cast(hire_date as date) as event_date
    from {{ ref('int_employees') }}
    where hire_date is not null

    union all

    select cast(termination_date as date) as event_date
    from {{ ref('int_employees') }}
    where termination_date is not null

),

bounds as (

    select
        coalesce(min(event_date), current_date()) as min_date,
        coalesce(max(event_date), current_date()) as max_date
    from candidate_dates

),

calendar as (

    select explode(sequence(min_date, max_date, interval 1 day)) as full_date
    from bounds

)

select
    cast(date_format(full_date, 'yyyyMMdd') as string) as sk_date,
    full_date,
    day(full_date) as day_number,
    month(full_date) as month_number,
    date_format(full_date, 'MMMM') as month_name,
    year(full_date) as year,
    date_format(full_date, 'EEEE') as day_of_week,
    case
        when dayofweek(full_date) in (1, 7) then true
        else false
    end as is_weekend

from calendar