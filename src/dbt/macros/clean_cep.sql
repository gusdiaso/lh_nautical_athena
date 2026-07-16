{% macro clean_cep(column_name) %}
    trim(
        regexp_replace(
            regexp_replace({{ column_name }}, '[^0-9]', ''),
            '^(\d{5})(\d{3})$',
            '\1-\2'
        )
    )
{% endmacro %}