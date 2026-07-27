-- Verifica que a data de término não é anterior à data de contratação e que funcionários ativos não possuem data de término.
-- Falha quando há data de término anterior à contratação ou funcionário ativo com data de término, evitando inconsistências no histórico de funcionários.
select
    nk_employee_id as employee_id
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
