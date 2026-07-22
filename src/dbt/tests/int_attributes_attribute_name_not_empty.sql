select
    attribute_id
    , attribute_name
from {{ ref('int_attributes') }}
where attribute_name is null or trim(attribute_name) = ''
