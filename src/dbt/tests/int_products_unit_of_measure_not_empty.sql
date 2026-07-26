-- Verifica que todo produto possui uma unidade de medida preenchida.
-- Falha quando unit_of_measure é nulo ou vazio, evitando produtos sem referência de medida.
select
    product_id
    , product_name
    , unit_of_measure
from {{ ref('int_products') }}
where unit_of_measure is null or trim(unit_of_measure) = ''
