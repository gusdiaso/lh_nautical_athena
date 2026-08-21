{% macro get_region_by_state(state_column) %}
case upper(trim({{ state_column }}))
    -- Norte
    when 'AC' then 'Norte'
    when 'AM' then 'Norte'
    when 'AP' then 'Norte'
    when 'PA' then 'Norte'
    when 'RO' then 'Norte'
    when 'RR' then 'Norte'
    when 'TO' then 'Norte'
    -- Nordeste
    when 'AL' then 'Nordeste'
    when 'BA' then 'Nordeste'
    when 'CE' then 'Nordeste'
    when 'MA' then 'Nordeste'
    when 'PB' then 'Nordeste'
    when 'PE' then 'Nordeste'
    when 'PI' then 'Nordeste'
    when 'RN' then 'Nordeste'
    when 'SE' then 'Nordeste'
    -- Centro-Oeste
    when 'DF' then 'Centro-Oeste'
    when 'GO' then 'Centro-Oeste'
    when 'MS' then 'Centro-Oeste'
    when 'MT' then 'Centro-Oeste'
    -- Sudeste
    when 'ES' then 'Sudeste'
    when 'MG' then 'Sudeste'
    when 'RJ' then 'Sudeste'
    when 'SP' then 'Sudeste'
    -- Sul
    when 'PR' then 'Sul'
    when 'RS' then 'Sul'
    when 'SC' then 'Sul'
    else null
end
{% endmacro %}
