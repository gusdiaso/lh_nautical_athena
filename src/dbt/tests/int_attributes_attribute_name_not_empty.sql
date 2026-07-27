-- Verifica que todo atributo possui um nome preenchido.
-- Falha quando attribute_name é nulo ou vazio, evitando registros sem identificação.
select
    attribute_id
    , attribute_name
from {{ ref('int_attributes') }}
where attribute_name is null or trim(attribute_name) = ''
