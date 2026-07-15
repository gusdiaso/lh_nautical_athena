with source as (

    select *
    from {{ ref('int_categories') }}

)

select
    md5(cast(category_id as string)) as sk_category,
    category_id as nk_category_id,
    name,
    slug,
    parent_category_id,
    is_active

from source
where category_id is not null