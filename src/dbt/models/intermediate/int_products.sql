with source as (

    select *
    from {{ ref('stg_products') }}

)

, base as (

    select
        product_id
        , brand_id
        , category_id
        , ncm_code
        , is_active
        , upper(trim(unit_of_measure)) as unit_of_measure
        , trim(product_name) as product_name
        , trim(description) as description
    from source
    where product_id is not null

)

, deduplicated as (

    select
        *
        , row_number() over (
            partition by product_id
            order by product_id
        ) as record_rank
    from base

)

, mapped as (

    select
        product_id
        , brand_id
        , category_id
        , ncm_code
        , unit_of_measure
        , is_active
        , case
            when
                lower(trim(product_name)) in ('tbd')
                then 'GPS Navegador Pro 7000'
            when
                lower(trim(product_name)) = 'asdf'
                and description like '%Defensa%'
                then 'Defensa NX6 Reforçada'
            when
                lower(trim(product_name)) = 'asdf' and description like '%Cabo%'
                then 'Cabo de Amarração T6 Premium'
            when
                product_name like 'Caboo Náutico%'
                then replace(product_name, 'Caboo Náutico', 'Cabo Náutico')
            when
                product_name like 'GPS Pltoter%'
                then replace(product_name, 'GPS Pltoter', 'GPS Plotter')
            -- nomes 100% inválidos ('João da Silva', 'Cliente Genérico',
            -- 'NAO INFORMADO', 'Genérico'); a descrição é confiável nesses
            -- casos, então usa ela pra descobrir a família e recompor o nome
            -- no padrão "<família> <product_id>" do restante do catálogo
            when
                lower(trim(product_name))
                in ('joão da silva', 'cliente genérico', 'nao informado', 'genérico')
                and lower(trim(description)) like 'motor%'
                then 'Motor de Popa ' || cast(product_id as string)
            when
                lower(trim(product_name))
                in ('joão da silva', 'cliente genérico', 'nao informado', 'genérico')
                and lower(trim(description)) like 'vela%'
                then 'Vela Mestra ' || cast(product_id as string)
            when
                lower(trim(product_name))
                in ('joão da silva', 'cliente genérico', 'nao informado', 'genérico')
                and lower(trim(description)) like 'bússola%'
                then 'Bússola de Bordo ' || cast(product_id as string)
            else product_name
        end as product_name
        , coalesce(
            -- description placeholder/lixo ('—', 'ver foto', 'Lorem ipsum...',
            -- 'TODO...') é tratada como ausente para cair no fallback abaixo
            case
                when trim(description) in ('—', 'ver foto') then null
                when lower(trim(description)) like 'lorem ipsum%' then null
                when lower(trim(description)) like 'todo%' then null
                else description
            end
            , case
                when
                    product_name like 'GPS Plotter%'
                    then
                        'GPS Plotter cartográfico com ecrã de alta resolução para navegação marítima'
                when
                    product_name like 'Tinta Antifouling%'
                    then
                        'Tinta anti-incrustante para proteção do casco contra organismos marinhos'
                when
                    product_name like 'Âncora Bruce%'
                    then
                        'Âncora tipo Bruce em aço galvanizado, ideal para fundos de areia e lama'
                when
                    product_name like 'Bússola%'
                    then 'Bússola magnética de navegação para embarcações'
                when
                    product_name like 'Colete Salva-Vidas%'
                    then
                        'Colete salva-vidas com certificação de segurança para navegação'
                when
                    product_name like 'Vela Mestra%'
                    then
                        'Vela mestra em poliéster de alta resistência para embarcações à vela'
                when
                    product_name like 'Hélice%'
                    then
                        'Hélice náutica em alumínio de alto desempenho para motores de popa'
                when
                    product_name like 'Defensa%'
                    then 'Defensa cilíndrica em PVC para proteção de embarcações'
                when
                    product_name like 'Sonar Transducer%'
                    then 'Transdutor de sonar para profundidade'
                when
                    product_name like 'Bateria Náutica%'
                    then 'Bateria estacionária 105Ah náutica'
                else description
            end
        ) as description
    from deduplicated
    where record_rank = 1

)

, classified as (

    select
        product_id
        , product_name
        , description
        , brand_id
        , ncm_code
        , unit_of_measure
        , is_active
        , case
            when lower(trim(description)) like 'motor%' then 4
            when lower(trim(description)) like 'vela%' then 6
            when lower(trim(description)) like 'tinta%' then 11
            when lower(trim(description)) like 'transdutor%' then 16
            when lower(trim(description)) like 'bússola%' then 17
            when lower(trim(description)) like 'defensa%' then 9
            when lower(trim(description)) like 'cabo%' then 2
            when lower(trim(description)) like 'colete%' then 3
            when lower(trim(description)) like 'hélice%' then 8
            when lower(trim(description)) like 'gps%' then 15
            when lower(trim(description)) like 'âncora%' then 7
            when lower(trim(description)) like 'bateria%' then 18
            else category_id
        end as category_id
    from mapped

)

select
    product_id
    , product_name
    , description
    , brand_id
    , category_id
    , ncm_code
    , unit_of_measure
    , is_active

from classified
order by product_id
