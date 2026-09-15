{{ config(
    post_hook=mask_post_hooks({
        "cpf": "mask_cpf",
        "email": "mask_email",
    })
) }}

with source as (

    select *
    from {{ ref('stg_employees') }}

)

, base as (

    select
        employee_id
        , primary_location_id
        , hire_date
        , termination_date
        , is_active
        , trim(full_name) as full_name
        , trim(cpf) as cpf
        , lower(trim(email)) as email
        , lower(trim(role)) as role
    from source
    where employee_id is not null

)

, deduplicated as (

    select
        *
        , row_number() over (
            partition by employee_id
            order by hire_date desc nulls last
        ) as record_rank
    from base

)

select
    employee_id
    , full_name
    , cpf
    , email
    , role
    , primary_location_id
    , hire_date
    , termination_date
    , is_active

from deduplicated
where record_rank = 1
