# Modelo Dimensional (Star Schema)

## Visão Geral

O modelo segue o padrão **Star Schema**, com **5 tabelas de dimensão** (verdes) conectadas a **6 tabelas de fato** (vermelhas). Todas as dimensões se relacionam com as fatos através de chaves substitutas (*surrogate keys*, prefixo `sk_`), permitindo relacionamento um-para-muitos (1:N) de cada dimensão para as fatos.

---

## Dimensões

### dim_customers (Clientes)

| Coluna | Descrição |
|--------|-----------|
| `sk_customer` | Chave substituta do cliente |
| `nk_customer_id` | Chave natural do cliente |
| `person_type` | Tipo de pessoa (Física/Jurídica) |
| `legal_name` | Razão social |
| `trade_name` | Nome fantasia |
| `tax_id` | CNPJ/CPF |
| `email` | E-mail de contato |
| `phone` | Telefone de contato |
| `address_type` | Tipo de endereço |
| `postal_code` | CEP |
| `complement` | Complemento do endereço |
| `number` | Número do endereço |
| `street` | Logradouro |
| `district` | Bairro |
| `city` | Cidade |
| `state` | Estado |
| `country` | País |
| `is_active` | Indicador de ativo |

### dim_date (Data)

| Coluna | Descrição |
|--------|-----------|
| `sk_date` | Chave substituta da data |
| `full_date` | Data completa |
| `day_number` | Número do dia |
| `month_number` | Número do mês |
| `month_name` | Nome do mês |
| `year` | Ano |
| `day_of_week` | Dia da semana |
| `is_weekend` | Indicador de fim de semana |

### dim_employees (Funcionários)

| Coluna | Descrição |
|--------|-----------|
| `sk_employee` | Chave substituta do funcionário |
| `nk_employee_id` | Chave natural do funcionário |
| `full_name` | Nome completo |
| `cpf` | CPF |
| `email` | E-mail |
| `role` | Cargo/Função |
| `hire_date` | Data de admissão |
| `termination_date` | Data de desligamento |
| `is_active` | Indicador de ativo |

### dim_suppliers (Fornecedores)

| Coluna | Descrição |
|--------|-----------|
| `sk_supplier` | Chave substituta do fornecedor |
| `nk_supplier_id` | Chave natural do fornecedor |
| `legal_name` | Razão social |
| `trade_name` | Nome fantasia |
| `tax_id` | CNPJ/CPF |
| `tax_id_type` | Tipo de documento fiscal |
| `country` | País |
| `contact_name` | Nome do contato |
| `email` | E-mail |
| `phone` | Telefone |
| `is_active` | Indicador de ativo |

### dim_products (Produtos)

| Coluna | Descrição |
|--------|-----------|
| `sk_product` | Chave substituta do produto |
| `nk_product_id` | Chave natural do produto |
| `sku` | SKU do produto |
| `barcode_ean` | Código de barras EAN |
| `product_name` | Nome do produto |
| `description` | Descrição do produto |
| `unit_of_measure` | Unidade de medida |
| `ncm_code` | Código NCM |
| `weight_kg` | Peso em kg |
| `brand_name` | Nome da marca |
| `brand_country` | País da marca |
| `brand_is_active` | Indicador de marca ativa |
| `category_name` | Nome da categoria |
| `category_slug` | Slug da categoria |
| `category_is_active` | Indicador de categoria ativa |
| `parent_category_name` | Nome da categoria pai |
| `parent_category_is_active` | Indicador de categoria pai ativa |
| `sale_price` | Preço de venda |
| `cost_price` | Preço de custo |
| `icms_rate` | Alíquota de ICMS |
| `ipi_rate` | Alíquota de IPI |
| `product_variant_is_active` | Indicador de variante ativa |

### dim_locations (Localizações)

| Coluna | Descrição |
|--------|-----------|
| `sk_location` | Chave substituta da localização |
| `nk_location_id` | Chave natural da localização |
| `name` | Nome da localização |
| `location_type` | Tipo de localização |
| `postal_code` | CEP |
| `number` | Número |
| `complement` | Complemento |
| `street` | Logradouro |
| `district` | Bairro |
| `city` | Cidade |
| `state` | Estado |
| `country` | País |
| `is_active` | Indicador de ativo |

---

## Tabelas de Fato (Fact Tables)

### fact_order_items (Itens de Pedido)

**Chaves:**
- `sk_date`
- `sk_product`
- `sk_location`
- `sk_employee`
- `sk_customer`

**Medidas:**

| Coluna | Descrição |
|--------|-----------|
| `order_number` | Número do pedido |
| `quantity` | Quantidade |
| `channel` | Canal de venda |
| `status` | Status do pedido |
| `unit_price` | Preço unitário |
| `icms_rate` | Alíquota de ICMS |
| `ipi_rate` | Alíquota de IPI |
| `discount_amount` | Valor do desconto |
| `gross_line_total` | Valor bruto da linha |
| `ipi_amount` | Valor do IPI |
| `net_line_total` | Valor líquido da linha |

### fact_payments (Pagamentos)

**Chaves:**
- `sk_date`
- `sk_customer`
- `sk_product`

**Medidas:**

| Coluna | Descrição |
|--------|-----------|
| `order_id` | ID do pedido |
| `method` | Método de pagamento |
| `installments` | Número de parcelas |
| `allocated_payment_amount` | Valor alocado do pagamento |
| `status` | Status do pagamento |

### fact_purchase_order_items (Itens de Pedido de Compra)

**Chaves:**
- `sk_date`
- `sk_product`
- `sk_location`
- `sk_employee`
- `sk_supplier`

**Medidas:**

| Coluna | Descrição |
|--------|-----------|
| `po_number` | Número do pedido de compra |
| `status` | Status |
| `currency` | Moeda |
| `quantity_ordered` | Quantidade solicitada |
| `unit_cost` | Custo unitário |
| `gross_line_total_cost` | Custo total bruto da linha |
| `expected_delivery_date` | Data prevista de entrega |

### fact_goods_receipt_items (Itens de Recebimento de Mercadoria)

**Chaves:**
- `sk_date`
- `sk_product`
- `sk_location`
- `sk_employee`
- `sk_supplier`

**Medidas:**

| Coluna | Descrição |
|--------|-----------|
| `receipt_id` | ID do recebimento |
| `purchase_order_id` | ID do pedido de compra |
| `quantity_ordered` | Quantidade solicitada |
| `quantity_received` | Quantidade recebida |

### fact_stock_movements (Movimentações de Estoque)

**Chaves:**
- `sk_date`
- `sk_product`
- `sk_location`
- `sk_employee`

**Medidas:**

| Coluna | Descrição |
|--------|-----------|
| `movement_type` | Tipo de movimentação |
| `reference_table` | Tabela de referência |
| `reference_id` | ID de referência |
| `quantity` | Quantidade |

### fact_return_items (Itens de Devolução)

**Chaves:**
- `sk_date`
- `sk_product`
- `sk_location`
- `sk_customer`
- `sk_supplier`

**Medidas:**

| Coluna | Descrição |
|--------|-----------|
| `return_number` | Número da devolução |
| `order_id` | ID do pedido |
| `order_item_id` | ID do item do pedido |
| `action` | Ação (troca/devolução) |
| `exchange_variant_id` | ID da variante de troca |
| `quantity` | Quantidade |
| `reason` | Motivo |
| `unit_refund_amount` | Valor unitário de reembolso |
| `total_refund_amount` | Valor total de reembolso |
| `status` | Status |

---

## Relacionamentos-Chave

| Regra | Descrição |
|-------|-----------|
| Todas as 6 fatos | Se ligam a `dim_date` e `dim_products` |
| `dim_locations` | Se relaciona com todas as fatos, exceto `fact_payments` |
| `dim_employees` | Se relaciona com `order_items`, `purchase_order_items`, `goods_receipt_items` e `stock_movements` (não `payments` nem `returns`) |
| `dim_customers` | Se relaciona com `order_items`, `payments` e `return_items` |
| `dim_suppliers` | Se relaciona com `purchase_order_items`, `goods_receipt_items` e `return_items` |
| `fact_goods_receipt_items` | Referencia `purchase_order_id` (ligação lógica com `fact_purchase_order_items`) |
| `fact_return_items` | Referencia `order_id` e `order_item_id` (ligação lógica com `fact_order_items`) |
