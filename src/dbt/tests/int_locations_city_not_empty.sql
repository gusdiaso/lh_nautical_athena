select
    location_id
    , location_name
    , city
from {{ ref('int_locations') }}
where city is null or trim(city) = ''
