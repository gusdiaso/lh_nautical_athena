{% macro sk_from_keys(columns) -%}
md5(
  concat_ws(
    '||',
    {%- for c in columns -%}
      cast({{ c }} as string){% if not loop.last %} , {% endif %}
    {%- endfor -%}
  )
)
{%- endmacro %}
