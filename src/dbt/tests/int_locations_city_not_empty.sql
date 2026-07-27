-- Verifica que toda localização possui uma cidade preenchida.
-- Falha quando city é nulo ou vazio, evitando localizações sem referência de cidade.
select
    location_id
    , location_name
    , city
from {{ ref('int_locations') }}
where city is null or trim(city) = ''
