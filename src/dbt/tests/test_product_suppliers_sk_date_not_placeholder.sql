select
    sk_product_supplier
from {{ ref('fact_product_suppliers') }}
where sk_date = cast(date_format(current_date(), 'yyyyMMdd') as string)
limit 1
