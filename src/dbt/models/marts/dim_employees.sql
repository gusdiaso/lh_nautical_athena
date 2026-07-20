-- ============================================================
-- dim_employees.sql
-- Grão:
-- uma linha por funcionário cadastrado
-- + membros técnicos validados com o cliente
-- ============================================================

with employees as (
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
    from {{ ref('int_employees') }}
)

, technical_employees as (
    select
        md5('employee||migracao_legado') as sk_employee
        , cast(-1 as bigint) as nk_employee_id
        , 'Migração do sistema legado' as full_name
        , cast(null as string) as cpf
        , cast(null as string) as email
        , 'sistema_legado' as role
        , cast(null as bigint) as nk_primary_location_id
        , cast(null as date) as hire_date
        , cast(null as date) as termination_date
        , false as is_active
        , true as is_technical_member

    union all

    select
        md5('employee||sistema_ecommerce') as sk_employee
        , cast(-2 as bigint) as nk_employee_id
        , 'Sistema E-commerce' as full_name
        , cast(null as string) as cpf
        , cast(null as string) as email
        , 'sistema_ecommerce' as role
        , cast(null as bigint) as nk_primary_location_id
        , cast(null as date) as hire_date
        , cast(null as date) as termination_date
        , true as is_active
        , true as is_technical_member

    union all

    select
        md5('employee||nao_informado') as sk_employee
        , cast(-3 as bigint) as nk_employee_id
        , 'Funcionário não informado' as full_name
        , cast(null as string) as cpf
        , cast(null as string) as email
        , 'nao_informado' as role
        , cast(null as bigint) as nk_primary_location_id
        , cast(null as date) as hire_date
        , cast(null as date) as termination_date
        , false as is_active
        , true as is_technical_member
)

, employees_dimension as (
    select
        md5(
            concat_ws(
                '||'
                , 'employee'
                , cast(employee_id as string)
            )
        ) as sk_employee
        , employee_id as nk_employee_id
        , full_name
        , cpf
        , email
        , role
        , primary_location_id as nk_primary_location_id
        , hire_date
        , termination_date
        , is_active
        , false as is_technical_member
    from employees
)

, final as (
    select
        sk_employee
        , nk_employee_id
        , full_name
        , cpf
        , email
        , role
        , nk_primary_location_id
        , hire_date
        , termination_date
        , is_active
        , is_technical_member
    from technical_employees

    union all

    select
        sk_employee
        , nk_employee_id
        , full_name
        , cpf
        , email
        , role
        , nk_primary_location_id
        , hire_date
        , termination_date
        , is_active
        , is_technical_member
    from employees_dimension
)

select * from final;