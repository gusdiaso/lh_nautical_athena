{% macro clean_cep(column_name) %}
    case
        when {{ column_name }} is not null
        then
            substr(
                regexp_replace({{ column_name }}, '[^0-9]', ''),
                1, 5
            ) || '-' ||
            substr(
                regexp_replace({{ column_name }}, '[^0-9]', ''),
                6, 3
            )
    end
{% endmacro %}