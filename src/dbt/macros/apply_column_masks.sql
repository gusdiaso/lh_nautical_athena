{% macro create_mask_functions() %}
  {#
    Cria (idempotente, CREATE OR REPLACE) as funcoes de mascara usadas pelos
    post-hooks dos models sensiveis e pelo apply_column_masks. Chamada no
    inicio do dbt_transform para que o job nao dependa implicitamente de
    apply_bronze_masks.py ter rodado antes na mesma execucao do orchestrator
    -- dbt_transform tambem e disparado manualmente para reprocessamento, e
    precisa ser autossuficiente.
  #}
  {% if execute %}
    {% set c = target.catalog %}
    {#
      Grupo fixo em lh_nautical_dev independente do target/catalogo: e o
      unico grupo com visao de dado real, em dev e em prod. lh_nautical_prod
      (e qualquer outro grupo) sempre ve o valor mascarado, nos dois
      catalogos -- nao ha ramificacao por ambiente aqui de proposito.
    #}
    {% set group = "lh_nautical_dev" %}

    {% for func in ["mask_full", "mask_cpf", "mask_email", "mask_phone"] %}
      {% do run_query(
        "create or replace function " ~ c ~ ".gold." ~ func ~ "(value string) "
        ~ "return case when is_member('" ~ group ~ "') then value else '***MASKED***' end"
      ) %}
    {% endfor %}
  {% endif %}
{% endmacro %}


{% macro mask_post_hooks(columns) %}
  {#
    Gera a lista de post-hooks que mascaram colunas sensiveis na sequencia
    imediata da criacao do model (mesma etapa, sem task/step separado depois).
    columns: dict coluna -> funcao de mascara, ex:
      {'tax_id': 'mask_full', 'email': 'mask_email', 'phone': 'mask_phone'}

    {{ this }} e {{ target.catalog }} ficam como texto literal de proposito:
    o post_hook e renderizado por dbt depois, no contexto do model que o
    declarou, quando a tabela ja existe.
  #}
  {% set hooks = [] %}
  {% for col, func in columns.items() %}
    {% do hooks.append(
      "alter table {{ this }} alter column " ~ col ~ " set mask {{ target.catalog }}.gold." ~ func
    ) %}
  {% endfor %}
  {{ return(hooks) }}
{% endmacro %}


{% macro apply_column_masks() %}
  {#
    Reaplica a mascara em todas as tabelas Silver e Gold sensiveis de uma vez.
    Os post-hooks em cada model (int_customers, int_employees, int_suppliers,
    dim_customers, dim_employees, dim_suppliers) ja aplicam a mascara direto
    apos cada tabela ser criada -- esta macro e uma segunda camada de
    garantia (ex: cobre um `dbt run` parcial fora do fluxo padrao), mantida
    por ser uma operacao de metadado, sem custo de reescrita de dados.
  #}
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
