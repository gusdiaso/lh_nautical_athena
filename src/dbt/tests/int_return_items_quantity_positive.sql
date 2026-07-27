-- Verifica que a quantidade devolvida nos itens de retorno é positiva.
-- Falha quando quantity_returned é zero ou negativo, evitando devoluções sem itens válidos.
select
    return_item_id
    , return_id
    , quantity_returned
from {{ ref('int_return_items') }}
where quantity_returned <= 0
