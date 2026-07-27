-- Verifica que toda localização possui um país preenchido.
-- Falha quando country é nulo ou vazio, evitando localizações sem referência geográfica.
select
    location_id
    , location_name
    , country
from {{ ref('int_locations') }}
where country is null or trim(country) = ''
