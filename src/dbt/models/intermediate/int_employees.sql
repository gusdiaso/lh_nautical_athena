with source as (

    select *
    from {{ ref('stg_employees') }}

),

base as (

    select
        employee_id,
        trim(full_name) as full_name,
        trim(cpf) as cpf,
        lower(trim(email)) as email,
        lower(trim(role)) as role,
        primary_location_id,
        hire_date,
        termination_date,
        is_active
    from source
    where employee_id is not null

),

deduplicated as (

    select
        *,
        row_number() over (
            partition by employee_id
            order by employee_id
        ) as record_rank
    from base

)

select
    employee_id,
    full_name,
    cpf,
    email,
    role,
    primary_location_id,
    hire_date,
    termination_date,
    is_active

from deduplicated
where record_rank = 1