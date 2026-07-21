select
    product_id
    , product_name
    , unit_of_measure
from {{ ref('int_products') }}
where unit_of_measure is null or trim(unit_of_measure) = ''
