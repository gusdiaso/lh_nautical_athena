# Modelo Dimensional (Star Schema)

## Visão Geral

O modelo dimensional do LH Nautical segue o padrão Star Schema com 6 dimensões e 6 fatos. As dimensões concentram o contexto descritivo e as fatos preservam o grão transacional para análise em BI.

As tabelas abaixo refletem a modelagem atual do repositório. Os detalhes finos de regras e testes ficam nos YAMLs de cada model em `src/dbt/models/marts/`.

## Dimensões

### dim_date

Dimensão calendário compartilhada pelas fatos.

| Coluna | Descrição |
|---|---|
| `sk_date` | Chave substituta da data no formato `YYYYMMDD`. |
| `full_date` | Data completa em nível diário. |
| `day_number` | Número do dia no mês. |
| `day_of_year` | Número sequencial do dia no ano. |
| `day_of_week_number` | Número do dia da semana. |
| `day_of_week_name` | Nome textual do dia da semana. |
| `week_of_year` | Número da semana no ano. |
| `month_number` | Número do mês. |
| `month_name` | Nome textual do mês. |
| `year_month` | Representação `YYYY-MM`. |
| `quarter_number` | Número do trimestre. |
| `quarter_name` | Rótulo do trimestre. |
| `year_quarter` | Representação `YYYY-TN`. |
| `semester_number` | Número do semestre. |
| `year_number` | Ano da data. |
| `is_weekend` | Indica fim de semana. |
| `is_high_season` | Indica alta temporada náutica. |

### dim_customers

Dimensão de clientes com seleção determinística de endereço.

| Coluna | Descrição |
|---|---|
| `sk_customer` | Chave substituta do cliente. |
| `nk_customer_id` | Identificador natural do cliente. |
| `person_type` | Tipo de pessoa do cliente. |
| `legal_name` | Nome legal ou razão social. |
| `trade_name` | Nome fantasia. |
| `tax_id` | Documento fiscal do cliente. |
| `state_registration` | Inscrição estadual. |
| `email` | E-mail principal. |
| `phone` | Telefone principal. |
| `nk_address_id` | Identificador natural do endereço selecionado. |
| `address_type` | Tipo do endereço. |
| `postal_code` | CEP do endereço. |
| `street` | Logradouro. |
| `number` | Número do endereço. |
| `complement` | Complemento do endereço. |
| `district` | Bairro. |
| `city` | Cidade. |
| `state` | Estado. |
| `country` | País. |
| `is_primary_address` | Indica se o endereço é o principal. |
| `is_active` | Indica se o cliente está ativo. |
| `is_technical_member` | Indica membro técnico da dimensão. |

### dim_employees

Dimensão de funcionários e membros técnicos.

| Coluna | Descrição |
|---|---|
| `sk_employee` | Chave substituta do funcionário. |
| `nk_employee_id` | Identificador natural ou técnico. |
| `full_name` | Nome do funcionário ou agente técnico. |
| `cpf` | CPF do funcionário. |
| `email` | E-mail do funcionário. |
| `role` | Cargo, função ou classificação técnica. |
| `nk_primary_location_id` | Identificador natural da localização principal. |
| `hire_date` | Data de admissão. |
| `termination_date` | Data de desligamento. |
| `is_active` | Indica se o registro está ativo. |
| `is_technical_member` | Indica se o registro é técnico. |

### dim_locations

Dimensão de lojas, armazéns e localizações conformadas.

| Coluna | Descrição |
|---|---|
| `sk_location` | Chave substituta da localização. |
| `nk_location_id` | Identificador natural da localização. |
| `location_name` | Nome da localização. |
| `location_type` | Tipo da localização. |
| `postal_code` | CEP. |
| `street` | Logradouro. |
| `number` | Número do endereço. |
| `complement` | Complemento. |
| `district` | Bairro. |
| `city` | Cidade. |
| `state` | Estado. |
| `country` | País. |
| `is_active` | Indica se a localização está ativa. |
| `is_technical_member` | Indica se o registro é técnico. |

### dim_products

Dimensão de produtos no grão de variante comercial.

| Coluna | Descrição |
|---|---|---|
| `sk_product` | Chave substituta da variante de produto. |
| `nk_product_variant_id` | Identificador natural da variante. |
| `nk_product_id` | Identificador natural do produto pai. |
| `sku` | Código SKU da variante. |
| `product_name` | Nome do produto. |
| `description` | Descrição do produto. |
| `nk_brand_id` | Identificador natural da marca. |
| `brand_name` | Nome da marca. |
| `brand_country` | País de origem da marca. |
| `is_brand_active` | Indica se a marca está ativa. |
| `nk_category_id` | Identificador natural da categoria. |
| `category_name` | Nome da categoria. |
| `category_slug` | Slug da categoria. |
| `is_category_active` | Indica se a categoria está ativa. |
| `ncm_code` | Código NCM do produto. |
| `unit_of_measure` | Unidade de medida. |
| `sale_price` | Preço cadastral de venda. |
| `cost_price` | Custo cadastral padrão. |
| `gross_margin_amount` | Margem bruta em valor. |
| `gross_margin_percentage` | Margem bruta percentual. |
| `weight_kg` | Peso da variante em quilogramas. |
| `icms_rate` | Alíquota de ICMS. |
| `ipi_rate` | Alíquota de IPI. |
| `total_tax_rate` | Soma das alíquotas de impostos. |
| `is_profitable` | Indica se o preço é superior ao custo. |
| `is_product_active` | Indica se o produto pai está ativo. |
| `is_variant_active` | Indica se a variante está ativa. |
| `is_technical_member` | Indica se o registro é técnico. |

### dim_suppliers

Dimensão de fornecedores para compras e recebimentos.

| Coluna | Descrição |
|---|---|
| `sk_supplier` | Chave substituta do fornecedor. |
| `nk_supplier_id` | Identificador natural do fornecedor. |
| `legal_name` | Razão social ou nome legal. |
| `trade_name` | Nome fantasia. |
| `country` | País do fornecedor. |
| `tax_id` | Documento fiscal. |
| `tax_id_type` | Tipo do documento fiscal. |
| `email` | E-mail do fornecedor. |
| `phone` | Telefone do fornecedor. |
| `contact_name` | Nome do contato principal. |
| `is_active` | Indica se o fornecedor está ativo. |
| `is_technical_member` | Indica se o registro é técnico. |

## Fatos

### fact_order_items

Fato de vendas no grão de um item por pedido.

| Coluna | Descrição |
|---|---|
| `sk_order_item` | Chave substituta do item do pedido. |
| `nk_order_item_id` | Identificador natural do item. |
| `nk_order_id` | Identificador natural do pedido. |
| `order_number` | Número comercial do pedido. |
| `sk_product` | Chave da dimensão de produtos. |
| `sk_customer` | Chave da dimensão de clientes. |
| `sk_location` | Chave da dimensão de localizações. |
| `sk_employee` | Chave da dimensão de funcionários. |
| `sk_date` | Chave da data do pedido. |
| `channel` | Canal de venda. |
| `order_status` | Status do pedido. |
| `quantity_ordered` | Quantidade vendida. |
| `unit_price` | Preço unitário de venda. |
| `gross_line_total` | Valor bruto da linha. |
| `allocated_discount_amount` | Desconto alocado ao item. |
| `net_line_total` | Valor líquido da linha. |
| `icms_rate` | Alíquota de ICMS. |
| `ipi_rate` | Alíquota de IPI. |
| `icms_amount` | Valor de ICMS da linha. |
| `ipi_amount` | Valor de IPI da linha. |
| `total_tax_amount` | Valor total de tributos. |
| `total_with_taxes` | Valor bruto com tributos. |
| `standard_unit_cost` | Custo padrão da variante. |
| `estimated_cost_of_goods_sold` | Custo estimado da mercadoria vendida. |
| `estimated_gross_profit` | Lucro bruto estimado. |
| `placed_at` | Data e hora de criação do pedido. |
| `is_cancelled` | Indica pedido cancelado. |
| `is_paid` | Indica pedido pago. |
| `is_confirmed` | Indica pedido confirmado. |
| `is_draft` | Indica pedido em rascunho. |
| `order_item_count` | Contador aditivo de itens. |

### fact_payments

Fato financeira no grão de uma transação de pagamento.

| Coluna | Descrição |
|---|---|
| `sk_payment` | Chave substituta do pagamento. |
| `nk_payment_id` | Identificador natural do pagamento. |
| `nk_order_id` | Identificador natural do pedido. |
| `order_number` | Número comercial do pedido. |
| `sk_customer` | Chave da dimensão de clientes. |
| `sk_location` | Chave da dimensão de localizações. |
| `sk_order_date` | Chave da data de criação do pedido. |
| `sk_payment_date` | Chave da data efetiva do pagamento. |
| `channel` | Canal de venda. |
| `order_status` | Status do pedido. |
| `method` | Método de pagamento. |
| `installments` | Quantidade de parcelas. |
| `payment_amount` | Valor original da transação. |
| `order_total` | Valor total do pedido associado. |
| `payment_status` | Status do pagamento. |
| `placed_at` | Data e hora de criação do pedido. |
| `paid_at` | Data e hora efetiva do pagamento. |
| `is_paid` | Indica pagamento concluído. |
| `is_refunded` | Indica pagamento estornado. |
| `is_pending` | Indica pagamento pendente. |
| `is_cancelled` | Indica pagamento cancelado. |
| `paid_amount` | Valor preenchido para pagamentos concluídos. |
| `refunded_amount` | Valor preenchido para pagamentos estornados. |
| `payment_count` | Contador aditivo de pagamentos. |

### fact_purchase_order_items

Fato de compras no grão de um item por pedido de compra.

| Coluna | Descrição |
|---|---|
| `sk_purchase_order_item` | Chave substituta do item de compra. |
| `nk_purchase_order_item_id` | Identificador natural do item. |
| `nk_purchase_order_id` | Identificador natural do pedido de compra. |
| `po_number` | Número comercial do pedido de compra. |
| `sk_product` | Chave da dimensão de produtos. |
| `sk_supplier` | Chave da dimensão de fornecedores. |
| `sk_location` | Chave da localização de destino. |
| `sk_employee` | Chave do funcionário comprador. |
| `sk_order_date` | Chave da data de emissão do pedido. |
| `sk_expected_delivery_date` | Chave da data prevista de entrega. |
| `purchase_order_status` | Status do pedido de compra. |
| `currency` | Moeda original da compra. |
| `exchange_rate_sell` | Taxa cambial associada ao pedido. |
| `quantity_ordered` | Quantidade comprada. |
| `unit_cost_original_currency` | Custo unitário na moeda original. |
| `line_total_original_currency` | Valor da linha na moeda original. |
| `unit_cost_brl` | Custo unitário convertido para BRL. |
| `line_total_brl` | Valor da linha convertido para BRL. |
| `placed_at` | Data e hora de emissão do pedido. |
| `expected_delivery_at` | Data prevista de entrega. |
| `is_expected_delivery_overdue` | Indica atraso na entrega esperada. |
| `purchase_order_item_count` | Contador aditivo de itens de compra. |

### fact_goods_receipt_items

Fato de recebimentos físicos no grão de um item por evento.

| Coluna | Descrição |
|---|---|
| `sk_goods_receipt_item` | Chave substituta do item recebido. |
| `nk_goods_receipt_item_id` | Identificador natural do item recebido. |
| `nk_goods_receipt_id` | Identificador natural do recebimento. |
| `nk_purchase_order_item_id` | Identificador natural do item comprado. |
| `nk_purchase_order_id` | Identificador natural do pedido de compra. |
| `po_number` | Número comercial do pedido de compra. |
| `sk_product` | Chave da dimensão de produtos. |
| `sk_supplier` | Chave da dimensão de fornecedores. |
| `sk_location` | Chave da localização de recebimento. |
| `sk_employee` | Chave do funcionário responsável. |
| `sk_receipt_date` | Chave da data do recebimento. |
| `sk_order_date` | Chave da data de emissão da ordem. |
| `sk_expected_delivery_date` | Chave da data prevista de entrega. |
| `purchase_order_status` | Status do pedido de compra. |
| `currency` | Moeda original da compra. |
| `exchange_rate_sell` | Taxa cambial associada ao pedido. |
| `quantity_ordered` | Quantidade originalmente comprada. |
| `quantity_received` | Quantidade recebida neste evento. |
| `cumulative_quantity_received` | Quantidade acumulada recebida. |
| `remaining_quantity_after_receipt` | Quantidade pendente após o evento. |
| `is_fully_received` | Indica recebimento completo. |
| `is_partial_receipt` | Indica recebimento parcial. |
| `unit_cost_original_currency` | Custo unitário na moeda original. |
| `received_value_original_currency` | Valor recebido na moeda original. |
| `received_value_brl` | Valor recebido convertido para BRL. |
| `placed_at` | Data e hora de emissão do pedido. |
| `expected_delivery_at` | Data prevista de entrega. |
| `received_at` | Data e hora do recebimento. |
| `delivery_variance_days` | Diferença em dias entre previsão e recebimento. |
| `is_late_receipt` | Indica atraso no recebimento. |
| `notes` | Observações operacionais do recebimento. |
| `goods_receipt_item_count` | Contador aditivo de itens recebidos. |

### fact_stock_movements

Fato de estoque no grão de uma movimentação individual.

| Coluna | Descrição |
|---|---|
| `sk_stock_movement` | Chave substituta da movimentação. |
| `nk_stock_movement_id` | Identificador natural da movimentação. |
| `sk_product` | Chave da dimensão de produtos. |
| `sk_location` | Chave da dimensão de localizações. |
| `sk_employee` | Chave da dimensão de funcionários. |
| `sk_date` | Chave da data da movimentação. |
| `reference_table` | Tabela operacional de origem. |
| `nk_reference_id` | Identificador natural do registro de referência. |
| `movement_type` | Tipo da movimentação. |
| `movement_direction` | Direção padronizada da movimentação. |
| `quantity` | Quantidade com sinal. |
| `absolute_quantity` | Magnitude absoluta da movimentação. |
| `notes` | Observações operacionais. |
| `occurred_at` | Data e hora da movimentação. |
| `is_legacy_migration` | Indica saldo inicial de migração legada. |
| `is_inbound` | Indica movimentação de entrada. |
| `is_outbound` | Indica movimentação de saída. |
| `movement_count` | Contador aditivo de movimentações. |

### fact_return_items

Fato de pós-venda no grão de um item pertencente a uma devolução.

| Coluna | Descrição |
|---|---|
| `sk_return_item` | Chave substituta do item devolvido. |
| `nk_return_item_id` | Identificador natural do item devolvido. |
| `nk_return_id` | Identificador natural da devolução. |
| `nk_order_item_id` | Identificador natural do item vendido originalmente. |
| `nk_order_id` | Identificador natural do pedido original. |
| `sk_returned_product` | Chave do produto devolvido. |
| `sk_exchange_product` | Chave do produto de troca. |
| `sk_customer` | Chave da dimensão de clientes. |
| `sk_location` | Chave da localização que recebeu a devolução. |
| `sk_date` | Chave da data da devolução. |
| `return_number` | Número comercial da devolução. |
| `return_status` | Status da devolução. |
| `original_reason` | Motivo original do ERP. |
| `reason_normalized` | Motivo textual normalizado. |
| `return_reason_group` | Grupo analítico do motivo. |
| `action` | Ação aplicada ao item. |
| `quantity_returned` | Quantidade devolvida. |
| `unit_refund_amount` | Valor unitário do reembolso. |
| `total_line_refund_amount` | Valor total reembolsado na linha. |
| `is_exchange` | Indica ação de troca. |
| `is_refund` | Indica ação de reembolso. |
| `return_has_refund_amount` | Indica se há valor de reembolso. |
| `returned_at` | Data e hora da devolução. |
| `returned_item_count` | Contador aditivo de itens devolvidos. |

## Fluxo

1. A camada Intermediate produz as tabelas analíticas de apoio.
2. As dimensões traduzem entidades de negócio em contexto descritivo.
3. As fatos ligam eventos transacionais às dimensões conformadas.
4. O consumo final ocorre sobre as tabelas `gold`.

## Referências

- [Camada Marts](marts.md)
- [Estratégia de testes](marts_tests.md)
- [README do projeto](../README.md)