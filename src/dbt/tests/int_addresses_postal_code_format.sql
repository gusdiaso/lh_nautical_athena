select *
from {{ ref('int_addresses') }}
where length(postal_code) <> 8