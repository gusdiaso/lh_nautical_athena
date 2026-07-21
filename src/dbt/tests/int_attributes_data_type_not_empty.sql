select
    attribute_id
    , attribute_name
    , data_type
from {{ ref('int_attributes') }}
where data_type is null or trim(data_type) = ''
