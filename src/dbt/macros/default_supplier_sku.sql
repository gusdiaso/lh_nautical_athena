{% macro default_supplier_sku(sku_column, supplier_id, product_variant_id) %}
case
    when {{ sku_column }} is null
        or upper(trim({{ sku_column }})) in ('TBD', '?', 'SEM-CODIGO', '')
    then concat(
        'SUP-'
        , lpad(cast({{ supplier_id }} as string), 3, '0')
        , '-'
        , lpad(cast({{ product_variant_id }} as string), 5, '0')
    )
    else trim({{ sku_column }})
end
{% endmacro %}
