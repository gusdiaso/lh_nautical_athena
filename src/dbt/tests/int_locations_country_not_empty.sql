select
    location_id
    , location_name
    , country
from {{ ref('int_locations') }}
where country is null or trim(country) = ''
