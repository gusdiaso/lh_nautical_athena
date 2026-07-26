-- Verifica que valores de atributos de variantes não contêm placeholders, dados de teste ou grafias incorretas conhecidas.
-- Falha quando attribute_value é um valor inválido ou contém erros de digitação, evitando dados sujos e classificações incorretas de produto.
select
    product_variant_id
    , attribute_id
    , attribute_name
    , original_value
    , attribute_value
from {{ ref('int_variant_attribute_values') }}
where
    lower(trim(attribute_value)) in (
        '?'
        , '??'
        , '???'
        , '.'
        , '-'
        , '--'
        , 'n/a'
        , 'todo'
        , 'tbd'
        , 'fixme'
        , 'test'
        , 'asdf'
        , 'xxx'
    )

    or (
        attribute_name = 'color'
        and attribute_value in (
            'Braco'
            , 'Brancoo'
            , 'Cinaz'
            , 'CCinza'
            , 'inza'
        )
    )

    or (
        attribute_name = 'size'
        and attribute_value = 'GX'
    )