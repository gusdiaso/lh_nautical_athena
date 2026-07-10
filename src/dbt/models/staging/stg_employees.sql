with source as (

    select *
    from {{ source('bronze', 'employees') }}

)

select
    id as employee_id,
    full_name,
    cpf,
    email,
    role,
    primary_location_id,
    hire_date,
    termination_date,
    is_active,
    created_at,
    updated_at

from source