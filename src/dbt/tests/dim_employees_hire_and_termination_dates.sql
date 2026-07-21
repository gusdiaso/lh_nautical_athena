select
    employee_id
    , full_name
    , hire_date
    , termination_date
    , is_active
from {{ ref('dim_employees') }}
where
    hire_date is not null
    and termination_date is not null
    and termination_date < hire_date
    or termination_date is not null
    and is_active = true
