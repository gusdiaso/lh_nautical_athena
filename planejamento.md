# Planejamento de Camadas Prata e Ouro — Lakehouse Nautical

---

## Objetivo

Este documento descreve o plano de implementação das camadas **Prata** (Silver) e **Ouro** (Gold) do projeto Lakehouse Nautical, utilizando **dbt** como ferramenta de transformação.

### O que é a camada Prata?

A camada Prata recebe os dados brutos da Bronze e aplica limpeza, padronização e validação de qualidade. Cada tabela Prata (chamada de `stg_*`) representa uma versão "higienizada" de uma tabela Bronze, com nomes de colunas padronizados e regras de qualidade aplicadas.

### O que é a camada Ouro?

A camada Ouro contém os dados modelados para consulta e análise. É aqui que montamos o **modelo dimensional** (Star Schema) com tabelas de dimensão (`dim_*`) e tabelas de fato (`fact_*`), prontas para serem consumidas por relatórios, dashboards e análises de negócio.

### Resultado Final Esperado

Ao final deste planejamento, teremos:

- **24 models Prata** — um para cada tabela Bronze, com limpeza e padronização
- **6 tabelas de dimensão** — dim_date, dim_customers, dim_products, dim_employees, dim_suppliers, dim_locations
- **6 tabelas de fato** — fact_order_items, fact_payments, fact_purchase_order_items, fact_goods_receipt_items, fact_stock_movements, fact_return_items
- **1 tabela de dimensão de câmbio** — dim_exchange_rates (para conversão de moedas estrangeiras)
- **Testes de qualidade** em todas as camadas
- **Documentação atualizada** do modelo de dados

### Prioridades de Negócio (nesta ordem)

1. **Fechamento contábil** — dados sólidos, auditáveis e consistentes para fechamento mensal/anual
2. **Financeiro** — visão ampla de receitas, pagamentos e fluxo de caixa
3. **Churn de clientes** — identificação de clientes que estão deixando de comprar
4. **Logística** — estoque, abastecimento e movimentação de mercadorias
5. **Outros domínios** — qualquer outra necessidade identificada durante a implementação

---

## 1. Visão Geral do Projeto

### Estrutura Atual

| Camada | Catálogo | Schema | Status |
|--------|----------|--------|--------|
| Bronze | `dev_lh_nautical` / `prod_lh_nautical` | `bronze` | Implementado |
| Prata | `dev_lh_nautical` / `prod_lh_nautical` | `silver` | Planejado |
| Ouro | `dev_lh_nautical` / `prod_lh_nautical` | `gold` | Planejado |

### Tabelas Bronze Existentes (25 tabelas)

**Referência (5):** categories, brands, locations, attributes, employees

**Clientes (2):** customers, addresses

**Fornecedores (1):** suppliers

**Produtos (4):** products, product_variants, variant_attribute_values, product_suppliers

**Pedidos de Compra (4):** purchase_orders, purchase_order_items, goods_receipts, goods_receipt_items

**Pedidos de Venda (4):** orders, order_items, payments, fiscal_invoices

**Devoluções (2):** returns, return_items

**Estoque (2):** stock_levels, stock_movements

**Câmbio (1):** exchange_rates (cotações PTAX do Banco Central — USD e EUR)

### Modelo Dimensional (Star Schema)

O modelo segue o padrão Star Schema com **6 dimensões** e **6 tabelas de fato**, conforme descrito em `docs/star_schema.md`.

**Flexibilidade:** O modelo não é imutável. Caso a validação com o time identifique necessidades adicionais (ex: dim_payment_methods, fact_inventory_snapshots), poderá ser adaptado.

---

## 2. Tabela de Câmbio — Uso na Camada Prata/Ouro

### Origem dos Dados

A tabela `exchange_rates` já está sendo ingerida na Bronze via job `extract_exchange_rates`, que busca cotações PTAX do Banco Central do Brasil. Ela contém cotações de compra e venda para **USD** (Dólar) e **EUR** (Euro).

### Estrutura da Tabela Bronze

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `exchange_date` | DATE | Data da cotação |
| `currency_code` | STRING | Código da moeda (USD ou EUR) |
| `exchange_rate_buy` | DOUBLE | Cotação de compra (média do dia) |
| `exchange_rate_sell` | DOUBLE | Cotação de venda (média do dia) |
| `_ingested_at` | TIMESTAMP | Data/hora da ingestão |
| `_source_path` | STRING | Origem dos dados |

### Onde será Usada

A tabela de câmbio será utilizada nas seguintes situações:

1. **fact_purchase_order_items** — Para converter o campo `currency` (moeda do pedido de compra) em valores em BRL, usando a cotação do dia do pedido

2. **fact_order_items** — Caso existam vendas em moeda estrangeira (verificar com o time se há essa necessidade)

3. **dim_exchange_rates** — Criação de uma dimensão de câmbio para análises de variação cambial

### Regras de Negócio para Câmbio

- **Conversão:** Usar `exchange_rate_sell` para converter valores de moeda estrangeira para BRL
- **Data de referência:** Usar a cotação do dia da transação (não do pagamento)
- **Caso não exista cotação no dia:** Usar a cotação do dia útil anterior mais próximo
- ⚠️ **Validar com time financeiro:** Confirmar regra de conversão e qual cotação utilizar (compra/venda)

---

## 3. Cronograma até 20/07

### Semana 1 (05/07 – 11/07): Infraestrutura + Prata Core

| Dia | Entregável | Responsável |
|-----|------------|-------------|
| 05-06/07 | Configuração do dbt (profiles, projeto, fontes) | Eng. Dados |
| 07-08/07 | Models Prata: referências (brands, categories, locations, employees, exchange_rates) | Eng. Dados |
| 09-10/07 | Models Prata: produtos (products, variants, suppliers) | Eng. Dados |
| 11/07 | Models Prata: clientes + validação com Fernanda | Eng. Dados + Fernanda |

### Semana 2 (12/07 – 18/07): Ouro Core + Fechamento Contábil + Financeiro

| Dia | Entregável | Responsável |
|-----|------------|-------------|
| 12-13/07 | Models Ouro: dimensões (dim_customers, dim_products, dim_date, dim_employees, dim_suppliers, dim_locations, dim_exchange_rates) | Eng. Dados |
| 14-15/07 | Models Ouro: fact_order_items + fact_payments (fechamento contábil e financeiro) | Eng. Dados |
| 16-17/07 | Models Ouro: fact_purchase_order_items + fact_goods_receipt_items (logística) | Eng. Dados |
| 18/07 | Testes de qualidade + documentação | Eng. Dados |

### Semana 3 (19/07 – 20/07): Finalização

| Dia | Entregável | Responsável |
|-----|------------|-------------|
| 19/07 | Models Ouro restantes (fact_stock_movements, fact_return_items) | Eng. Dados |
| 20/07 | Validação final, deploy em produção, documentação | Eng. Dados |

---

## 4. Camada Prata (por Domínio de Negócio)

### 4.1 Configuração Inicial do dbt

**Estrutura de pastas:**

```
src/dbt/
├── dbt_project.yml          (configuração do projeto)
├── profiles.yml             (conexão com Databricks)
├── packages.yml             (pacotes auxiliares)
├── models/
│   ├── sources/
│   │   └── _fontes_bronze.yml   (definição das fontes)
│   ├── staging/
│   │   ├── _models_prata.yml    (metadados dos models)
│   │   └── stg_*.sql            (models de limpeza)
│   └── marts/
│       ├── _models_ouro.yml     (metadados dos models)
│       └── dim_*.sql / fact_*.sql (models dimensionais)
├── tests/
└── macros/
```

**Configurações principais:**

- `dbt_project.yml`: Nome do projeto `lh_nautical`, materialização padrão `table`, schema padrão `silver`
- `profiles.yml`: Conexão Databricks com catálogos `dev_lh_nautical` (desenvolvimento) e `prod_lh_nautical` (produção)
- `packages.yml`: Pacote `dbt_utils` para funções auxiliares (chaves substitutas, geração de datas)

⚠️ **Pendência:** Confirmar Endpoint ID do SQL Warehouse para conexão dbt.

---

### 4.2 Domínio: Referências

**Prioridade:** Suporte (necessário para todas as outras camadas)

#### Models Prata

| Model | Tabela Bronze | Grão | Regras de Qualidade |
|-------|---------------|------|---------------------|
| `stg_brands` | `bronze.brands` | 1 registro = 1 marca | `id` não nulo, `name` não nulo |
| `stg_categories` | `bronze.categories` | 1 registro = 1 categoria | `id` não nulo, `name` não nulo |
| `stg_locations` | `bronze.locations` | 1 registro = 1 localização | `id` não nulo, `name` não nulo |
| `stg_attributes` | `bronze.attributes` | 1 registro = 1 atributo | `id` não nulo, `name` não nulo |
| `stg_employees` | `bronze.employees` | 1 registro = 1 funcionário | `id` não nulo, `full_name` não nulo |

**Colunas esperadas por model:**

- **stg_brands:** brand_id, brand_name, brand_country, brand_is_active, created_at, updated_at
- **stg_categories:** category_id, category_name, slug, parent_category_id, category_is_active, created_at, updated_at
- **stg_locations:** location_id, name, location_type, postal_code, number, complement, street, district, city, state, country, is_active
- **stg_attributes:** attribute_id, name, data_type
- **stg_employees:** employee_id, full_name, cpf, email, role, primary_location_id, hire_date, termination_date, is_active

**Testes recomendados:**
- não nulo: chaves primárias e nomes
- único: chaves primárias
- valores aceitos: is_active (verdadeiro/falso)

---

### 4.3 Domínio: Câmbio

**Prioridade:** Alta (Fechamento contábil + Financeiro — pedidos de compra em moeda estrangeira)

#### Model Prata

| Model | Tabela Bronze | Grão | Regras de Qualidade |
|-------|---------------|------|---------------------|
| `stg_exchange_rates` | `bronze.exchange_rates` | 1 registro = 1 cotação por data e moeda | `exchange_date` não nulo, `currency_code` não nulo, `exchange_rate_sell` não nulo |

**Colunas esperadas:**

- `stg_exchange_rates`: exchange_date, currency_code, exchange_rate_buy, exchange_rate_sell

**Testes recomendados:**
- não nulo: exchange_date, currency_code, exchange_rate_sell
- único: exchange_date + currency_code (composição)
- valores aceitos: currency_code ('USD', 'EUR')

**Observações:**
- A tabela Bronze já é ingerida incrementalmente via job `extract_exchange_rates`
- Cotações são médias diárias de compra e venda (PTAX)
- Dados disponíveis a partir de 01/07/2019

---

### 4.4 Domínio: Produtos

**Prioridade:** Suporte (necessário para Ouro)

#### Models Prata

| Model | Tabela Bronze | Grão | Regras de Qualidade |
|-------|---------------|------|---------------------|
| `stg_products` | `bronze.products` | 1 registro = 1 produto | `id` não nulo, `name` não nulo |
| `stg_product_variants` | `bronze.product_variants` | 1 registro = 1 variante/SKU | `id` não nulo, `sku` não nulo |
| `stg_variant_attribute_values` | `bronze.variant_attribute_values` | 1 registro = 1 combinação variante-atributo | `product_variant_id` não nulo, `attribute_id` não nulo |
| `stg_product_suppliers` | `bronze.product_suppliers` | 1 registro = 1 combinação produto-fornecedor | `product_variant_id` não nulo, `supplier_id` não nulo |

**Colunas esperadas por model:**

- **stg_products:** product_id, product_name, description, brand_id, category_id, ncm_code, unit_of_measure, product_is_active, created_at, updated_at
- **stg_product_variants:** variant_id, product_id, sku, barcode_ean, sale_price, cost_price, weight_kg, icms_rate, ipi_rate, variant_is_active, created_at, updated_at
- **stg_variant_attribute_values:** product_variant_id, attribute_id, value
- **stg_product_suppliers:** product_variant_id, supplier_id, supplier_sku, last_quoted_cost, lead_time_days, is_preferred, created_at, updated_at

**Testes recomendados:**
- não nulo: chaves primárias, sku, product_name
- único: chaves primárias
- relacionamento: brand_id → stg_brands.brand_id, category_id → stg_categories.category_id

---

### 4.5 Domínio: Clientes

**Prioridade:** Alta (Fechamento contábil + Financeiro + Churn)

#### Models Prata

| Model | Tabela Bronze | Grão | Regras de Qualidade |
|-------|---------------|------|---------------------|
| `stg_customers` | `bronze.customers` | 1 registro = 1 cliente | `id` não nulo, `legal_name` não nulo |
| `stg_addresses` | `bronze.addresses` | 1 registro = 1 endereço | `id` não nulo, `customer_id` não nulo |

**Colunas esperadas por model:**

- **stg_customers:** customer_id, person_type, legal_name, trade_name, tax_id, state_registration, email, phone, customer_is_active, created_at, updated_at
- **stg_addresses:** address_id, customer_id, address_type, postal_code, street, number, complement, district, city, state, country, is_primary

**Testes recomendados:**
- não nulo: customer_id, legal_name
- único: customer_id
- valores aceitos: person_type ('F', 'J')

---

### 4.6 Domínio: Fornecedores

**Prioridade:** Média (Logística)

#### Model Prata

| Model | Tabela Bronze | Grão | Regras de Qualidade |
|-------|---------------|------|---------------------|
| `stg_suppliers` | `bronze.suppliers` | 1 registro = 1 fornecedor | `id` não nulo, `legal_name` não nulo |

**Colunas esperadas:**

- `stg_suppliers`: supplier_id, legal_name, trade_name, supplier_country, tax_id, tax_id_type, email, phone, contact_name, supplier_is_active, created_at, updated_at

**Testes recomendados:**
- não nulo: supplier_id, legal_name
- único: supplier_id

---

### 4.7 Domínio: Pedidos de Venda

**Prioridade:** Alta (Fechamento contábil + Financeiro)

#### Models Prata

| Model | Tabela Bronze | Grão | Regras de Qualidade |
|-------|---------------|------|---------------------|
| `stg_orders` | `bronze.orders` | 1 registro = 1 pedido | `id` não nulo, `order_number` não nulo |
| `stg_order_items` | `bronze.order_items` | 1 registro = 1 item de pedido | `id` não nulo, `order_id` não nulo |
| `stg_payments` | `bronze.payments` | 1 registro = 1 transação de pagamento | `id` não nulo, `order_id` não nulo |
| `stg_fiscal_invoices` | `bronze.fiscal_invoices` | 1 registro = 1 nota fiscal | `id` não nulo, `order_id` não nulo |

**Colunas esperadas por model:**

- **stg_orders:** order_id, order_number, channel, customer_id, employee_id, location_id, order_status, subtotal, discount_amount, total, order_placed_at, created_at, updated_at
- **stg_order_items:** order_item_id, order_id, product_variant_id, quantity, unit_price, icms_rate, ipi_rate, line_total
- **stg_payments:** payment_id, order_id, method, installments, amount, status, paid_at, created_at, updated_at
- **stg_fiscal_invoices:** invoice_id, order_id, nfe_number, nfe_access_key, series, issued_at, status, total_amount, xml_storage_uri, created_at, updated_at

**Testes recomendados:**
- não nulo: order_id, order_number
- único: order_id
- relacionamento: customer_id → stg_customers.customer_id, employee_id → stg_employees.employee_id, location_id → stg_locations.location_id

---

### 4.8 Domínio: Pedidos de Compra

**Prioridade:** Média (Logística)

#### Models Prata

| Model | Tabela Bronze | Grão | Regras de Qualidade |
|-------|---------------|------|---------------------|
| `stg_purchase_orders` | `bronze.purchase_orders` | 1 registro = 1 pedido de compra | `id` não nulo, `po_number` não nulo |
| `stg_purchase_order_items` | `bronze.purchase_order_items` | 1 registro = 1 item de compra | `id` não nulo, `purchase_order_id` não nulo |
| `stg_goods_receipts` | `bronze.goods_receipts` | 1 registro = 1 recebimento | `id` não nulo, `purchase_order_id` não nulo |
| `stg_goods_receipt_items` | `bronze.goods_receipt_items` | 1 registro = 1 item recebido | `id` não nulo, `goods_receipt_id` não nulo |

**Colunas esperadas por model:**

- **stg_purchase_orders:** purchase_order_id, po_number, supplier_id, buyer_id, destination_location_id, status, currency, subtotal, total, placed_at, expected_delivery_at, created_at, updated_at
- **stg_purchase_order_items:** purchase_order_item_id, purchase_order_id, product_variant_id, quantity_ordered, unit_cost, line_total
- **stg_goods_receipts:** goods_receipt_id, purchase_order_id, received_by_employee_id, received_at, notes, created_at
- **stg_goods_receipt_items:** goods_receipt_item_id, goods_receipt_id, purchase_order_item_id, quantity_received

**Testes recomendados:**
- não nulo: purchase_order_id, po_number
- único: purchase_order_id
- relacionamento: supplier_id → stg_suppliers.supplier_id, buyer_id → stg_employees.employee_id

---

### 4.9 Domínio: Estoque

**Prioridade:** Média (Logística)

#### Models Prata

| Model | Tabela Bronze | Grão | Regras de Qualidade |
|-------|---------------|------|---------------------|
| `stg_stock_levels` | `bronze.stock_levels` | 1 registro = 1 saldo por variante/localização | `product_variant_id` não nulo, `location_id` não nulo |
| `stg_stock_movements` | `bronze.stock_movements` | 1 registro = 1 movimentação | `id` não nulo, `product_variant_id` não nulo |

**Colunas esperadas por model:**

- **stg_stock_levels:** product_variant_id, location_id, quantity_on_hand, reorder_point, updated_at
- **stg_stock_movements:** movement_id, product_variant_id, location_id, movement_type, quantity, reference_table, reference_id, employee_id, notes, occurred_at, created_at

**Testes recomendados:**
- não nulo: product_variant_id, location_id
- relacionamento: employee_id → stg_employees.employee_id

---

### 4.10 Domínio: Devoluções

**Prioridade:** Média (Financeiro)

#### Models Prata

| Model | Tabela Bronze | Grão | Regras de Qualidade |
|-------|---------------|------|---------------------|
| `stg_returns` | `bronze.returns` | 1 registro = 1 devolução | `id` não nulo, `return_number` não nulo |
| `stg_return_items` | `bronze.return_items` | 1 registro = 1 item devolvido | `id` não nulo, `return_id` não nulo |

**Colunas esperadas por model:**

- **stg_returns:** return_id, return_number, order_id, customer_id, received_at_location_id, status, reason, total_refund_amount, created_at, updated_at
- **stg_return_items:** return_item_id, return_id, order_item_id, quantity, action, exchange_variant_id, unit_refund_amount

**Testes recomendados:**
- não nulo: return_id, return_number
- único: return_id
- relacionamento: customer_id → stg_customers.customer_id, order_id → stg_orders.order_id

---

## 5. Camada Ouro (por Domínio de Negócio)

### 5.1 Dimensões

#### dim_date (Data)

- **Grão:** 1 registro = 1 dia
- **Geração:** Utilizar dbt_utils.date_spine para gerar sequência de datas
- **Colunas:** sk_date (chave substituta numérica no formato yyyyMMdd), full_date, day_number, month_number, month_name, year, day_of_week, is_weekend
- **Testes:** único: sk_date, não nulo: sk_date, full_date

---

#### dim_customers (Clientes)

- **Grão:** 1 registro = 1 cliente (atualização tipo 1)
- **Chave substituta:** sk_customer gerada via dbt_utils.generate_surrogate_key
- **Fontes:** stg_customers + stg_addresses (endereço principal)
- **Colunas:** sk_customer, nk_customer_id, person_type, legal_name, trade_name, tax_id, email, phone, address_type, postal_code, complement, number, street, district, city, state, country, is_active
- **Testes:** único: sk_customer, não nulo: sk_customer, nk_customer_id

---

#### dim_products (Produtos)

- **Grão:** 1 registro = 1 variante de produto (SKU)
- **Chave substituta:** sk_product gerada via dbt_utils.generate_surrogate_key
- **Fontes:** stg_products + stg_product_variants + stg_brands + stg_categories (com auto-relacionamento para categoria pai)
- **Colunas:** sk_product, nk_product_id, sku, barcode_ean, product_name, description, unit_of_measure, ncm_code, weight_kg, brand_name, brand_country, brand_is_active, category_name, category_slug, category_is_active, parent_category_name, parent_category_is_active, sale_price, cost_price, icms_rate, ipi_rate, product_variant_is_active
- **Testes:** único: sk_product, não nulo: sk_product, nk_product_id, sku

---

#### dim_employees (Funcionários)

- **Grão:** 1 registro = 1 funcionário
- **Chave substituta:** sk_employee gerada via dbt_utils.generate_surrogate_key
- **Fontes:** stg_employees
- **Colunas:** sk_employee, nk_employee_id, full_name, cpf, email, role, hire_date, termination_date, is_active
- **Testes:** único: sk_employee, não nulo: sk_employee, nk_employee_id

---

#### dim_suppliers (Fornecedores)

- **Grão:** 1 registro = 1 fornecedor
- **Chave substituta:** sk_supplier gerada via dbt_utils.generate_surrogate_key
- **Fontes:** stg_suppliers
- **Colunas:** sk_supplier, nk_supplier_id, legal_name, trade_name, tax_id, tax_id_type, country, contact_name, email, phone, is_active
- **Testes:** único: sk_supplier, não nulo: sk_supplier, nk_supplier_id

---

#### dim_locations (Localizações)

- **Grão:** 1 registro = 1 localização
- **Chave substituta:** sk_location gerada via dbt_utils.generate_surrogate_key
- **Fontes:** stg_locations
- **Colunas:** sk_location, nk_location_id, name, location_type, postal_code, number, complement, street, district, city, state, country, is_active
- **Testes:** único: sk_location, não nulo: sk_location, nk_location_id

---

#### dim_exchange_rates (Câmbio)

- **Grão:** 1 registro = 1 cotação por data e moeda
- **Chave substituta:** sk_exchange_rate gerada via dbt_utils.generate_surrogate_key
- **Fontes:** stg_exchange_rates
- **Colunas:** sk_exchange_rate, nk_exchange_date, currency_code, exchange_rate_buy, exchange_rate_sell
- **Testes:** único: sk_exchange_rate, não nulo: sk_exchange_rate, nk_exchange_date, currency_code

**Observação:** Esta dimensão poderá ser expandida para incluir variação cambial, médias móveis, etc., conforme necessidade de análise.

---

### 5.2 Tabelas de Fato

#### fact_order_items (Itens de Pedido de Venda)

- **Grão:** 1 registro = 1 item de pedido de venda
- **Chaves:** sk_date, sk_product, sk_location, sk_employee, sk_customer
- **Medidas:** order_number, quantity, channel, status, unit_price, icms_rate, ipi_rate, discount_amount, gross_line_total, ipi_amount, net_line_total
- **Fontes:** stg_order_items + stg_orders + dim_date + dim_products + dim_locations + dim_employees + dim_customers
- **Testes:** não nulo: sk_date, sk_product, relacionamento: sk_date → dim_date.sk_date
- ⚠️ **Pendência:** Confirmar regra de cálculo de discount_amount e ipi_amount com time de negócio

---

#### fact_payments (Pagamentos)

- **Grão:** 1 registro = 1 transação de pagamento
- **Chaves:** sk_date, sk_customer, sk_product
- **Medidas:** order_id, method, installments, allocated_payment_amount, status
- **Fontes:** stg_payments + stg_orders + stg_order_items + dim_date + dim_customers + dim_products
- ⚠️ **Pendência:** Confirmar granularidade de sk_product — se 1 pagamento pode ter múltiplos produtos

---

#### fact_purchase_order_items (Itens de Pedido de Compra)

- **Grão:** 1 registro = 1 item de pedido de compra
- **Chaves:** sk_date, sk_product, sk_location, sk_employee, sk_supplier
- **Medidas:** po_number, status, currency, quantity_ordered, unit_cost, gross_line_total_cost, expected_delivery_date
- **Fontes:** stg_purchase_order_items + stg_purchase_orders + dim_date + dim_products + dim_locations + dim_employees + dim_suppliers
- **Uso da tabela de câmbio:** Converter `gross_line_total_cost` para BRL usando `exchange_rate_sell` da dim_exchange_rates (quando currency != 'BRL')

---

#### fact_goods_receipt_items (Itens de Recebimento de Mercadoria)

- **Grão:** 1 registro = 1 item recebido
- **Chaves:** sk_date, sk_product, sk_location, sk_employee, sk_supplier
- **Medidas:** receipt_id, purchase_order_id, quantity_ordered, quantity_received
- **Fontes:** stg_goods_receipt_items + stg_goods_receipts + stg_purchase_order_items + stg_purchase_orders + dim_date + dim_products + dim_locations + dim_employees + dim_suppliers

---

#### fact_stock_movements (Movimentações de Estoque)

- **Grão:** 1 registro = 1 movimentação de estoque
- **Chaves:** sk_date, sk_product, sk_location, sk_employee
- **Medidas:** movement_type, reference_table, reference_id, quantity
- **Fontes:** stg_stock_movements + dim_date + dim_products + dim_locations + dim_employees

---

#### fact_return_items (Itens de Devolução)

- **Grão:** 1 registro = 1 item devolvido
- **Chaves:** sk_date, sk_product, sk_location, sk_customer, sk_supplier
- **Medidas:** return_number, order_id, order_item_id, action, exchange_variant_id, quantity, reason, unit_refund_amount, total_refund_amount, status
- **Fontes:** stg_return_items + stg_returns + stg_order_items + dim_date + dim_products + dim_locations + dim_customers + dim_suppliers
- ⚠️ **Pendência:** Confirmar relationship com dim_suppliers em devoluções — pode ser necessário via order_items → product_suppliers

---

## 6. Testes e Qualidade de Dados

### 6.1 Tipos de Teste por Camada

| Tipo de Teste | Camada | Descrição |
|---------------|--------|-----------|
| não nulo | Prata + Ouro | Colunas-chave não podem ter valores nulos |
| único | Prata + Ouro | Chaves primárias devem ser únicas |
| relacionamento | Prata + Ouro | Integridade referencial entre tabelas |
| valores aceitos | Prata | Valores de enum devem estar na lista permitida |
| atualidade | Fontes | Verificar se Bronze está atualizada |

### 6.2 Testes de Qualidade por Domínio

| Domínio | Teste Crítico | Colunas |
|---------|---------------|---------|
| Fechamento contábil | Valores financeiros não nulos | gross_line_total, net_line_total |
| Financeiro | Pagamentos com status válido | status IN ('pending', 'approved', 'rejected') |
| Churn | Clientes com dados completos | customer_id, email, phone |
| Logística | Quantidades positivas | quantity > 0 |

---

## 7. Riscos e Pontos em Aberto

### 7.1 Riscos Técnicos

| Risco | Impacto | Mitigação |
|-------|---------|-----------|
| dbt não configurado no projeto | Atraso na Semana 1 | Configurar profiles.yml e dbt_project.yml prioritariamente |
| Endpoint SQL Warehouse não definido | Impossível conectar dbt | Validar com time de infraestrutura |
| Chaves substitutas podem conflitar | Dados duplicados em dimensões | Usar dbt_utils.generate_surrogate_key com hashes MD5 |
| Granularidade de payments vs products | Dados incorretos em fact_payments | Validar regra de negócio com Fernanda |

### 7.2 Dados Faltantes

| Dado | Impacto | Ação Necessária |
|------|---------|-----------------|
| Regra de cálculo de IPI/ICMS | Valores incorretos em fechamento contábil | Validar com time financeiro |
| Mapeamento supplier_id em returns | Impossível ligação com dim_suppliers | Verificar se product_suppliers resolve |
| Campo channel na dimensão de pedidos | Análise de vendas por canal | Confirmar se deve estar em dim ou fact |
| Histórico de preços (SCD) | Perda de auditabilidade | Considerar SCD Tipo 2 para dim_products |

### 7.3 Pontos em Aberto com Fernanda Dittert

| Tema | Pergunta | Prioridade |
|------|----------|------------|
| Documentação de fontes | Confirmação dos nomes das tabelas Bronze | Alta |
| Regras de negócio | Cálculo de descontos e impostos | Alta |
| Churn de clientes | Definição de "cliente inativo" (período sem compra?) | Alta |
| Fechamento contábil | Quais campos são obrigatórios para auditoria? | Alta |
| Granularidade de pagamentos | 1 pagamento pode ter múltiplos produtos? | Média |
| Star schema atual | Validação do modelo dimensional proposto ou necessidade de ajustes? | Alta |
| Câmbio | Confirmar regra de conversão (compra/venda) e data de referência | Alta |

---

## 8. Próximos Passos Imediatos

### Imediatos (05-06/07)

1. Criar estrutura dbt — dbt_project.yml, profiles.yml, packages.yml
2. Definir fontes — Arquivo _fontes_bronze.yml com todas as 25 tabelas (incluindo exchange_rates)
3. Configurar schemas — silver e gold no Unity Catalog
4. Validar endpoint — Confirmar SQL Warehouse para conexão dbt

### Curto Prazo (07-11/07)

5. Implementar Prata: referências — stg_brands, stg_categories, stg_locations, stg_employees
6. Implementar Prata: câmbio — stg_exchange_rates
7. Implementar Prata: produtos — stg_products, stg_product_variants, stg_variant_attribute_values, stg_product_suppliers
8. Implementar Prata: clientes — stg_customers, stg_addresses
9. Validar com Fernanda — Dicionário de dados e regras de negócio

### Médio Prazo (12-18/07)

10. Implementar Ouro: dimensões — Todas as 7 dimensões (incluindo dim_exchange_rates)
11. Implementar Ouro: fact_order_items — Prioridade para fechamento contábil
12. Implementar Ouro: fact_payments — Prioridade para fechamento contábil
13. Implementar testes — Todos os testes de qualidade

### Final (19-20/07)

14. Implementar Ouro: fatos restantes — fact_purchase_order_items, fact_goods_receipt_items, fact_stock_movements, fact_return_items
15. Deploy em produção — Configurar job dbt no Databricks
16. Documentação final — Atualizar README e dicionário de dados

---

## Apêndice: Diagrama de Dependências

### Camada Prata (25 models)

```
Fontes Bronze
    │
    ├── stg_brands
    ├── stg_categories
    ├── stg_locations
    ├── stg_attributes
    ├── stg_employees
    ├── stg_exchange_rates
    ├── stg_customers
    ├── stg_addresses
    ├── stg_suppliers
    ├── stg_products
    ├── stg_product_variants
    ├── stg_variant_attribute_values
    ├── stg_product_suppliers
    ├── stg_orders
    ├── stg_order_items
    ├── stg_payments
    ├── stg_fiscal_invoices
    ├── stg_purchase_orders
    ├── stg_purchase_order_items
    ├── stg_goods_receipts
    ├── stg_goods_receipt_items
    ├── stg_stock_levels
    ├── stg_stock_movements
    ├── stg_returns
    └── stg_return_items
```

### Camada Ouro (13 models)

```
Camada Prata
    │
    ├── dim_date
    ├── dim_customers
    ├── dim_products
    ├── dim_employees
    ├── dim_suppliers
    ├── dim_locations
    ├── dim_exchange_rates
    │
    └── fact_order_items
        fact_payments
        fact_purchase_order_items
        fact_goods_receipt_items
        fact_stock_movements
        fact_return_items
```
