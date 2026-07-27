-- Verifica que todo atributo possui um tipo de dado definido.
-- Falha quando data_type é nulo ou vazio, evitando atributos sem classificação de tipo.
select
    attribute_id
    , attribute_name
    , data_type
from {{ ref('int_attributes') }}
where data_type is null or trim(data_type) = ''
