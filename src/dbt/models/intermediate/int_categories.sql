with source as (

    select *
    from {{ ref('stg_categories') }}

)

, base as (

    select
        category_id
        , parent_category_id
        , is_active
        , trim(category_name) as category_name
        , lower(trim(slug)) as slug
    from source
    where category_id is not null

)

, deduplicated as (

    select
        *
        , row_number() over (
            partition by category_id
            order by category_id
        ) as record_rank
    from base

)

, corrected as (

    select
        category_id
        , is_active
        , case category_id
            when 13 then 'Segurança'
            else trim(category_name)
        end as category_name
        , case category_id
            when 7 then 'ancoras'
            else slug
        end as slug
        , case category_id
            when 3 then 13  -- Coletes Salva-Vidas → Segurança
            when 4 then 1   -- Motores → Equipamentos
            when 5 then 1   -- Eletrônica Náutica → Equipamentos
            when 6 then 1   -- Velas → Equipamentos
            when 7 then 1   -- Âncoras → Equipamentos
            when 8 then 1   -- Hélices → Equipamentos
            when 9 then 1   -- Acessórios de Convés → Equipamentos
            when 10 then 5   -- Iluminação → Eletrônica Náutica
            when 11 then 12  -- Pintura Marítima → Manutenção
            when 12 then 1   -- Manutenção → Equipamentos
            when 14 then 1   -- Pesca → Equipamentos
            -- 1 Equipamentos, 2 Cabos, 13 Segurança → top-level
        end as parent_category_id
    from deduplicated
    where record_rank = 1

)

, new_categories as (

    -- subcategorias novas de "Eletrônica Náutica" (5): antes as 4 famílias
    -- abaixo (bússola, gps, transdutor/sonar, bateria) caíam todas juntas
    -- direto em category_id=5, sem distinção entre si
    select
        15 as category_id
        , 'GPS & Plotters' as category_name
        , 'gps-e-plotters' as slug
        , 5 as parent_category_id
        , true as is_active

    union all

    select
        16 as category_id
        , 'Sonares e Transdutores' as category_name
        , 'sonares-e-transdutores' as slug
        , 5 as parent_category_id
        , true as is_active

    union all

    select
        17 as category_id
        , 'Instrumentos de Navegação' as category_name
        , 'instrumentos-de-navegacao' as slug
        , 5 as parent_category_id
        , true as is_active

    union all

    select
        18 as category_id
        , 'Baterias e Sistemas Elétricos' as category_name
        , 'baterias-e-sistemas-eletricos' as slug
        , 5 as parent_category_id
        , true as is_active

)

select
    category_id
    , category_name
    , slug
    , parent_category_id
    , is_active

from corrected

union all

select
    category_id
    , category_name
    , slug
    , parent_category_id
    , is_active

from new_categories

order by category_id
