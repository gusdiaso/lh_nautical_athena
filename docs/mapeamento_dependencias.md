# Mapeamento de Dependências — lh_nautical

## Arquitetura

```
bronze (source) → staging ({{ source }}) → intermediate ({{ ref('stg_*') }}) → marts ({{ ref('int_*') }})
```

| Camada | Schema | Materialização | Models |
|--------|--------|---------------|--------|
| **Staging** | — | ephemeral (CTE) | 24 |
| **Intermediate** | `silver` | table | 24 |
| **Marts** | `gold` | table | 12 |

---

## 1. Staging (24 modelos)

Cada modelo lê diretamente de uma tabela fonte no schema `bronze`.

| Modelo | Fonte (source) |
|--------|----------------|
| `stg_addresses` | `bronze.addresses` |
| `stg_attributes` | `bronze.attributes` |
| `stg_brands` | `bronze.brands` |
| `stg_categories` | `bronze.categories` |
| `stg_customers` | `bronze.customers` |
| `stg_employees` | `bronze.employees` |
| `stg_exchange_rates` | `bronze.exchange_rates` |
| `stg_goods_receipt_items` | `bronze.goods_receipt_items` |
| `stg_goods_receipts` | `bronze.goods_receipts` |
| `stg_locations` | `bronze.locations` |
| `stg_order_items` | `bronze.order_items` |
| `stg_orders` | `bronze.orders` |
| `stg_payments` | `bronze.payments` |
| `stg_product_suppliers` | `bronze.product_suppliers` |
| `stg_product_variants` | `bronze.product_variants` |
| `stg_products` | `bronze.products` |
| `stg_purchase_order_items` | `bronze.purchase_order_items` |
| `stg_purchase_orders` | `bronze.purchase_orders` |
| `stg_return_items` | `bronze.return_items` |
| `stg_returns` | `bronze.returns` |
| `stg_stock_levels` | `bronze.stock_levels` |
| `stg_stock_movements` | `bronze.stock_movements` |
| `stg_suppliers` | `bronze.suppliers` |
| `stg_variant_attribute_values` | `bronze.variant_attribute_values` |

---

## 2. Intermediate (24 modelos)

Cada modelo lê de um ou mais modelos **staging** (ou outros intermediate).

| Modelo | Referências ({{ ref }}) |
|--------|-------------------------|
| `int_addresses` | `stg_addresses` |
| `int_attributes` | `stg_attributes` |
| `int_brands` | `stg_brands` |
| `int_categories` | `stg_categories` |
| `int_customers` | `stg_customers` |
| `int_employees` | `stg_employees` |
| `int_exchange_rates` | `stg_exchange_rates` |
| `int_goods_receipts` | `stg_goods_receipts` |
| `int_goods_receipt_items` | `stg_goods_receipt_items` |
| `int_locations` | `stg_locations` |
| `int_orders` | `stg_orders` |
| `int_order_items` | `stg_order_items` |
| `int_payments` | `stg_payments` |
| `int_products` | `stg_products` |
| `int_product_suppliers` | `stg_product_suppliers` |
| `int_product_variants` | `stg_product_variants` |
| `int_purchase_orders` | `stg_purchase_orders` + **`int_exchange_rates`** |
| `int_purchase_order_items` | `stg_purchase_order_items` |
| `int_returns` | `stg_returns` |
| `int_return_items` | `stg_return_items` |
| `int_stock_levels` | `stg_stock_levels` |
| `int_stock_movements` | `stg_stock_movements` |
| `int_suppliers` | `stg_suppliers` |
| `int_variant_attribute_values` | `stg_variant_attribute_values` + `stg_attributes` |

### Dependências cruzadas (intermediate → intermediate)

| Modelo | Depende de |
|--------|-----------|
| `int_purchase_orders` | `int_exchange_rates` |
| `int_variant_attribute_values` | *(apenas staging)* |

---

## 3. Marts (12 modelos)

### 3.1 Dimensões (6)

| Modelo | Referências ({{ ref }}) |
|--------|-------------------------|
| `dim_customers` | `int_customers`, `int_addresses` |
| `dim_products` | `int_product_variants`, `int_products`, `int_brands`, `int_categories` |
| `dim_suppliers` | `int_suppliers` |
| `dim_locations` | `int_locations` |
| `dim_employees` | `int_employees` |
| `dim_date` | `int_orders`, `int_stock_movements`, `int_payments`, `int_purchase_orders`, `int_goods_receipts`, `int_exchange_rates` |

### 3.2 Fatos (6)

| Modelo | Referências ({{ ref }}) |
|--------|-------------------------|
| `fact_order_items` | `int_order_items`, `int_orders`, `dim_products`, `dim_customers`, `dim_locations`, `dim_employees`, `dim_date` |
| `fact_purchase_order_items` | `int_purchase_order_items`, `int_purchase_orders`, `dim_products`, `dim_suppliers`, `dim_locations`, `dim_employees`, `dim_date` |
| `fact_payments` | `int_payments`, `int_orders`, `dim_customers`, `dim_locations`, `dim_date` |
| `fact_return_items` | `int_return_items`, `int_returns`, `int_order_items`, `dim_products`, `dim_customers`, `dim_locations`, `dim_date` |
| `fact_stock_movements` | `int_stock_movements`, `dim_products`, `dim_locations`, `dim_employees`, `dim_date` |
| `fact_goods_receipt_items` | `int_goods_receipt_items`, `int_goods_receipts`, `int_purchase_order_items`, `int_purchase_orders`, `dim_products`, `dim_suppliers`, `dim_locations`, `dim_employees`, `dim_date` |

---

## 4. Árvore de Dependência Reversa (quem usa cada modelo)

### Bronze → Staging

| Tabela Bronze | Modelo Staging |
|---------------|---------------|
| `bronze.addresses` | `stg_addresses` |
| `bronze.attributes` | `stg_attributes` |
| `bronze.brands` | `stg_brands` |
| `bronze.categories` | `stg_categories` |
| `bronze.customers` | `stg_customers` |
| `bronze.employees` | `stg_employees` |
| `bronze.exchange_rates` | `stg_exchange_rates` |
| `bronze.goods_receipt_items` | `stg_goods_receipt_items` |
| `bronze.goods_receipts` | `stg_goods_receipts` |
| `bronze.locations` | `stg_locations` |
| `bronze.order_items` | `stg_order_items` |
| `bronze.orders` | `stg_orders` |
| `bronze.payments` | `stg_payments` |
| `bronze.product_suppliers` | `stg_product_suppliers` |
| `bronze.product_variants` | `stg_product_variants` |
| `bronze.products` | `stg_products` |
| `bronze.purchase_order_items` | `stg_purchase_order_items` |
| `bronze.purchase_orders` | `stg_purchase_orders` |
| `bronze.return_items` | `stg_return_items` |
| `bronze.returns` | `stg_returns` |
| `bronze.stock_levels` | `stg_stock_levels` |
| `bronze.stock_movements` | `stg_stock_movements` |
| `bronze.suppliers` | `stg_suppliers` |
| `bronze.variant_attribute_values` | `stg_variant_attribute_values` |

### Staging → Intermediate

| Modelo Staging | Usado por (intermediate) |
|----------------|--------------------------|
| `stg_addresses` | `int_addresses` |
| `stg_attributes` | `int_attributes`, **`int_variant_attribute_values`** |
| `stg_brands` | `int_brands` |
| `stg_categories` | `int_categories` |
| `stg_customers` | `int_customers` |
| `stg_employees` | `int_employees` |
| `stg_exchange_rates` | `int_exchange_rates` |
| `stg_goods_receipt_items` | `int_goods_receipt_items` |
| `stg_goods_receipts` | `int_goods_receipts` |
| `stg_locations` | `int_locations` |
| `stg_order_items` | `int_order_items` |
| `stg_orders` | `int_orders` |
| `stg_payments` | `int_payments` |
| `stg_product_suppliers` | `int_product_suppliers` |
| `stg_product_variants` | `int_product_variants` |
| `stg_products` | `int_products` |
| `stg_purchase_order_items` | `int_purchase_order_items` |
| `stg_purchase_orders` | `int_purchase_orders` |
| `stg_return_items` | `int_return_items` |
| `stg_returns` | `int_returns` |
| `stg_stock_levels` | `int_stock_levels` |
| `stg_stock_movements` | `int_stock_movements` |
| `stg_suppliers` | `int_suppliers` |
| `stg_variant_attribute_values` | `int_variant_attribute_values` |

### Intermediate → Marts

| Modelo Intermediate | Usado por (marts) |
|---------------------|-------------------|
| `int_addresses` | `dim_customers` |
| `int_attributes` | *(nenhum)* |
| `int_brands` | `dim_products` |
| `int_categories` | `dim_products` |
| `int_customers` | `dim_customers` |
| `int_employees` | `dim_employees`, `fact_order_items`, `fact_purchase_order_items`, `fact_stock_movements`, `fact_goods_receipt_items` |
| `int_exchange_rates` | `int_purchase_orders` (intermediate), `dim_date` |
| `int_goods_receipt_items` | `fact_goods_receipt_items` |
| `int_goods_receipts` | `fact_goods_receipt_items`, `dim_date` |
| `int_locations` | `dim_locations`, `fact_order_items`, `fact_purchase_order_items`, `fact_payments`, `fact_return_items`, `fact_stock_movements`, `fact_goods_receipt_items` |
| `int_order_items` | `fact_order_items`, `fact_return_items` |
| `int_orders` | `fact_order_items`, `fact_payments`, `dim_date` |
| `int_payments` | `fact_payments`, `dim_date` |
| `int_product_suppliers` | *(nenhum)* |
| `int_product_variants` | `dim_products` |
| `int_products` | `dim_products` |
| `int_purchase_order_items` | `fact_purchase_order_items`, `fact_goods_receipt_items` |
| `int_purchase_orders` | `fact_purchase_order_items`, `fact_goods_receipt_items`, `dim_date` |
| `int_return_items` | `fact_return_items` |
| `int_returns` | `fact_return_items` |
| `int_stock_levels` | *(nenhum)* |
| `int_stock_movements` | `fact_stock_movements`, `dim_date` |
| `int_suppliers` | `dim_suppliers` |
| `int_variant_attribute_values` | *(nenhum)* |

### Marts → Marts (dependências entre dimensões e fatos)

| Modelo Marts | Usado por |
|--------------|-----------|
| `dim_customers` | `fact_order_items`, `fact_payments`, `fact_return_items` |
| `dim_products` | `fact_order_items`, `fact_purchase_order_items`, `fact_return_items`, `fact_stock_movements`, `fact_goods_receipt_items` |
| `dim_suppliers` | `fact_purchase_order_items`, `fact_goods_receipt_items` |
| `dim_locations` | `fact_order_items`, `fact_purchase_order_items`, `fact_payments`, `fact_return_items`, `fact_stock_movements`, `fact_goods_receipt_items` |
| `dim_employees` | `fact_order_items`, `fact_purchase_order_items`, `fact_stock_movements`, `fact_goods_receipt_items` |
| `dim_date` | `fact_order_items`, `fact_purchase_order_items`, `fact_payments`, `fact_return_items`, `fact_stock_movements`, `fact_goods_receipt_items` |

---

## 5. Modelos sem dependentes (folhas)

Modelos que não são usados por nenhum outro modelo:

| Camada | Modelo |
|--------|--------|
| intermediate | `int_attributes` |
| intermediate | `int_product_suppliers` |
| intermediate | `int_stock_levels` |
| intermediate | `int_variant_attribute_values` |

---

## 6. Dependências por Ordem de Execução

```
stg_*
  ├── int_*  (cada int_X depende de stg_X)
  │   ├── int_purchase_orders ─── depende de int_exchange_rates
  │   └── int_variant_attribute_values ─── depende de stg_attributes + stg_variant_attribute_values
  │
  └── marts
      ├── dim_customers      ─── int_customers, int_addresses
      ├── dim_products       ─── int_products, int_product_variants, int_brands, int_categories
      ├── dim_suppliers      ─── int_suppliers
      ├── dim_locations      ─── int_locations
      ├── dim_employees      ─── int_employees
      ├── dim_date           ─── int_orders, int_stock_movements, int_payments, int_purchase_orders, int_goods_receipts, int_exchange_rates
      │
      ├── fact_payments              ─── dims + int_payments, int_orders
      ├── fact_order_items           ─── dims + int_order_items, int_orders
      ├── fact_return_items          ─── dims + int_return_items, int_returns, int_order_items
      ├── fact_stock_movements       ─── dims + int_stock_movements
      ├── fact_purchase_order_items  ─── dims + int_purchase_order_items, int_purchase_orders
      └── fact_goods_receipt_items   ─── dims + int_goods_receipt_items, int_goods_receipts, int_purchase_order_items, int_purchase_orders
```
