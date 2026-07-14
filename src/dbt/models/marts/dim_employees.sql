with source as (

    select *
    from {{ ref('int_employees') }}

)

select
    md5(cast(employee_id as string)) as sk_employee,
    employee_id as nk_employee_id,
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
where employee_id is not null