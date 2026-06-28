"""Configuracoes do pipeline de extracao lh_nautical."""

# ── Conexao com o SQL Server ─────────────────────────────
JDBC_URL = (
    "jdbc:sqlserver://18.209.218.63:4563"
    ";databaseName=lh_nautical"
    ";encrypt=true"
    ";trustServerCertificate=true"
    ";loginTimeout=60"
    ";socketTimeout=600"
)
SECRET_SCOPE = "lh_nautical"
SECRET_KEY = "secret_lh_nautical_bd"
SOURCE_SCHEMA = "dbo"

# ── Tabela de destino ────────────────────────────────────
DEFAULT_CATALOG = "dev_lh_nautical"
DEFAULT_SCHEMA = "bronze"

# ── Lista de tabelas para extrair ────────────────────────
TABLES = [
    # Referencia
    "categories",
    "brands",
    "locations",
    "attributes",
    "employees",
    # Clientes
    "customers",
    "addresses",
    # Fornecedores
    "suppliers",
    # Produtos
    "products",
    "product_variants",
    "variant_attribute_values",
    "product_suppliers",
    # Pedidos de compra
    "purchase_orders",
    "purchase_order_items",
    "goods_receipts",
    "goods_receipt_items",
    # Pedidos de venda
    "orders",
    "order_items",
    "payments",
    "fiscal_invoices",
    # Devolucoes
    "returns",
    "return_items",
    # Estoque
    "stock_levels",
    "stock_movements",
]

# ── Lista de moedas para extrair ────────────────────────
CURRENCIES = ["USD", "EUR"]
