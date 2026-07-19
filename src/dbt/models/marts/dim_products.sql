-- ============================================================
-- dim_products.sql
-- Grão:
-- uma linha por variante de produto (SKU)
-- + membro técnico para produto não informado
--
-- A dimensão consolida atributos da variante, do produto,
-- da marca e da categoria utilizada diretamente pelo produto.
--
-- A hierarquia de categoria pai não é utilizada neste modelo.
-- ============================================================

with product_variants as (
    select
        product_variant_id
        , product_id
        , sku
        , barcode_ean
        , sale_price
        , cost_price
        , weight_kg
        , icms_rate
        , ipi_rate
        , is_active
        , gross_margin_amount
        , gross_margin_percentage
        , total_tax_rate
        , is_profitable
    from {{ ref('int_product_variants') }}
)

, products as (
    select
        product_id
        , product_name
        , description
        , brand_id
        , category_id
        , ncm_code
        , unit_of_measure
        , is_active
    from {{ ref('int_products') }}
)

, brands as (
    select
        brand_id
        , brand_name
        , country
        , is_active
    from {{ ref('int_brands') }}
)

, categories as (
    select
        category_id
        , category_name
        , slug
        , is_active
    from {{ ref('int_categories') }}
)

, technical_product as (
    select
        md5('product||nao_informado') as sk_product
        , cast(-1 as bigint) as nk_product_variant_id
        , cast(-1 as bigint) as nk_product_id
        , cast(null as string) as sku
        , cast(null as string) as barcode_ean
        , 'Produto não informado' as product_name
        , cast(null as string) as description
        , cast(null as bigint) as nk_brand_id
        , 'Marca não informada' as brand_name
        , cast(null as string) as brand_country
        , false as is_brand_active
        , cast(null as bigint) as nk_category_id
        , 'Categoria não informada' as category_name
        , cast(null as string) as category_slug
        , false as is_category_active
        , cast(null as string) as ncm_code
        , cast(null as string) as unit_of_measure
        , cast(null as decimal(18, 2)) as sale_price
        , cast(null as decimal(18, 2)) as cost_price
        , cast(null as decimal(18, 2)) as gross_margin_amount
        , cast(null as decimal(18, 2)) as gross_margin_percentage
        , cast(null as decimal(18, 2)) as weight_kg
        , cast(null as decimal(18, 2)) as icms_rate
        , cast(null as decimal(18, 2)) as ipi_rate
        , cast(null as decimal(18, 2)) as total_tax_rate
        , false as is_profitable
        , false as is_product_active
        , false as is_variant_active
        , true as is_technical_member
)

, products_dimension as (
    select
        md5(
            concat_ws(
                '||'
                , 'product'
                , cast(product_variants.product_variant_id as string)
            )
        ) as sk_product
        , product_variants.product_variant_id as nk_product_variant_id
        , product_variants.product_id as nk_product_id
        , product_variants.sku
        , product_variants.barcode_ean
        , products.product_name
        , products.description
        , products.brand_id as nk_brand_id
        , coalesce(
            brands.brand_name
            , 'Marca não informada'
        ) as brand_name
        , brands.country as brand_country
        , coalesce(
            brands.is_active
            , false
        ) as is_brand_active
        , products.category_id as nk_category_id
        , coalesce(
            categories.category_name
            , 'Categoria não informada'
        ) as category_name
        , categories.slug as category_slug
        , coalesce(
            categories.is_active
            , false
        ) as is_category_active
        , products.ncm_code
        , products.unit_of_measure
        , product_variants.sale_price
        , product_variants.cost_price
        , product_variants.gross_margin_amount
        , product_variants.gross_margin_percentage
        , product_variants.weight_kg
        , product_variants.icms_rate
        , product_variants.ipi_rate
        , product_variants.total_tax_rate
        , product_variants.is_profitable
        , products.is_active as is_product_active
        , product_variants.is_active as is_variant_active
        , false as is_technical_member
    from product_variants
    left join products
        on product_variants.product_id = products.product_id
    left join brands
        on products.brand_id = brands.brand_id
    left join categories
        on products.category_id = categories.category_id
)

, final as (
    select
        sk_product
        , nk_product_variant_id
        , nk_product_id
        , sku
        , barcode_ean
        , product_name
        , description
        , nk_brand_id
        , brand_name
        , brand_country
        , is_brand_active
        , nk_category_id
        , category_name
        , category_slug
        , is_category_active
        , ncm_code
        , unit_of_measure
        , sale_price
        , cost_price
        , gross_margin_amount
        , gross_margin_percentage
        , weight_kg
        , icms_rate
        , ipi_rate
        , total_tax_rate
        , is_profitable
        , is_product_active
        , is_variant_active
        , is_technical_member
    from technical_product

    union all

    select
        sk_product
        , nk_product_variant_id
        , nk_product_id
        , sku
        , barcode_ean
        , product_name
        , description
        , nk_brand_id
        , brand_name
        , brand_country
        , is_brand_active
        , nk_category_id
        , category_name
        , category_slug
        , is_category_active
        , ncm_code
        , unit_of_measure
        , sale_price
        , cost_price
        , gross_margin_amount
        , gross_margin_percentage
        , weight_kg
        , icms_rate
        , ipi_rate
        , total_tax_rate
        , is_profitable
        , is_product_active
        , is_variant_active
        , is_technical_member
    from products_dimension
)

select * from final