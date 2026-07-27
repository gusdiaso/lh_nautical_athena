{% macro apply_column_masks() %}
  {% if execute %}
    {% set c = target.catalog %}

    {% set masks = [
      { "t": c ~ ".silver.int_customers", "col": "tax_id",  "m": c ~ ".gold.mask_full" },
      { "t": c ~ ".silver.int_customers", "col": "email",   "m": c ~ ".gold.mask_email" },
      { "t": c ~ ".silver.int_customers", "col": "phone",   "m": c ~ ".gold.mask_phone" },
      { "t": c ~ ".silver.int_employees", "col": "cpf",     "m": c ~ ".gold.mask_cpf" },
      { "t": c ~ ".silver.int_employees", "col": "email",   "m": c ~ ".gold.mask_email" },
      { "t": c ~ ".silver.int_suppliers", "col": "tax_id",  "m": c ~ ".gold.mask_full" },
      { "t": c ~ ".silver.int_suppliers", "col": "email",   "m": c ~ ".gold.mask_email" },
      { "t": c ~ ".silver.int_suppliers", "col": "phone",   "m": c ~ ".gold.mask_phone" },
      { "t": c ~ ".gold.dim_customers",   "col": "tax_id",  "m": c ~ ".gold.mask_full" },
      { "t": c ~ ".gold.dim_customers",   "col": "email",   "m": c ~ ".gold.mask_email" },
      { "t": c ~ ".gold.dim_customers",   "col": "phone",   "m": c ~ ".gold.mask_phone" },
      { "t": c ~ ".gold.dim_employees",   "col": "cpf",     "m": c ~ ".gold.mask_cpf" },
      { "t": c ~ ".gold.dim_employees",   "col": "email",   "m": c ~ ".gold.mask_email" },
      { "t": c ~ ".gold.dim_suppliers",   "col": "tax_id",  "m": c ~ ".gold.mask_full" },
      { "t": c ~ ".gold.dim_suppliers",   "col": "email",   "m": c ~ ".gold.mask_email" },
      { "t": c ~ ".gold.dim_suppliers",   "col": "phone",   "m": c ~ ".gold.mask_phone" },
    ] %}

    {% for m in masks %}
      {% do run_query("ALTER TABLE " ~ m.t ~ " ALTER COLUMN " ~ m.col ~ " SET MASK " ~ m.m) %}
    {% endfor %}
  {% endif %}
{% endmacro %}
