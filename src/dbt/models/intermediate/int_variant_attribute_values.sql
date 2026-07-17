with variant_attribute_values as (
    select
        product_variant_id
        , attribute_id
        , value
    from {{ ref('stg_variant_attribute_values') }}
)

, attributes as (
    select
        attribute_id
        , attribute_name
        , data_type
    from {{ ref('stg_attributes') }}
)

, base as (
    select
        variant_attribute_values.product_variant_id
        , variant_attribute_values.attribute_id
        , attributes.attribute_name
        , attributes.data_type as attribute_data_type
        , variant_attribute_values.value as original_value
        , case
            when lower(trim(variant_attribute_values.value)) in (
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
            ) then null

            when attributes.attribute_name = 'color'
                and lower(trim(variant_attribute_values.value)) in (
                    'braco'
                    , 'brancoo'
                )
                then 'Branco'

            when attributes.attribute_name = 'color'
                and lower(trim(variant_attribute_values.value)) in (
                    'cinaz'
                    , 'ccinza'
                    , 'inza'
                )
                then 'Cinza'

            when attributes.attribute_name = 'color'
                then initcap(lower(trim(variant_attribute_values.value)))

            when attributes.attribute_name = 'size'
                and upper(trim(variant_attribute_values.value)) = 'GX'
                then 'XG'

            when attributes.attribute_name = 'size'
                then upper(trim(variant_attribute_values.value))

            when attributes.attribute_name = 'material'
                then initcap(lower(trim(variant_attribute_values.value)))

            else trim(variant_attribute_values.value)
        end as attribute_value
    from variant_attribute_values
    left join attributes
        on variant_attribute_values.attribute_id = attributes.attribute_id
    where variant_attribute_values.product_variant_id is not null
        and variant_attribute_values.attribute_id is not null
)

, deduplicated as (
    select
        product_variant_id
        , attribute_id
        , attribute_name
        , attribute_data_type
        , original_value
        , attribute_value
        , row_number() over (
            partition by
                product_variant_id
                , attribute_id
            order by
                product_variant_id
                , attribute_id
        ) as record_rank
    from base
)

, final as (
    select
        product_variant_id
        , attribute_id
        , attribute_name
        , attribute_data_type
        , original_value
        , attribute_value
    from deduplicated
    where record_rank = 1
)

select * from final