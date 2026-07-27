# Contexto de Banco de Dados: Esquema e Dicionário de Dados

## Tabelas de Domínio e Relacionamentos Base

### `addresses`

**Descrição:** Esta tabela armazena os endereços associados aos clientes, permitindo múltiplos endereços (como cobrança e entrega) para a mesma pessoa. Ela centraliza os dados de localização física cruciais para logística e faturamento.
**Colunas:**

- **`id`**: Identificador único do endereço (Chave Primária - PK).
- **`customer_id`**: Referência ao cliente proprietário do endereço (Chave Estrangeira - FK).
- **`address_type`**: Categoria do endereço, como entrega, cobrança ou residencial.
- **`postal_code`**: Código postal (CEP) da localidade.
- **`street`**: Nome da rua, avenida ou logradouro.
- **`number`**: Número do imóvel no endereço.
- **`complement`**: Informações adicionais do endereço, como bloco, apartamento ou sala.
- **`district`**: Bairro onde o imóvel está localizado.
- **`city`**: Cidade da localização do imóvel.
- **`state`**: Estado ou província da localização.
- **`country`**: País da localização do endereço.
- **`is_primary`**: Indicador booleano que define se este é o endereço principal do cliente.

### `attributes`

**Descrição:** Tabela de domínio que define as propriedades customizáveis que os produtos podem ter, como "Cor", "Tamanho" ou "Voltagem". Ela serve como base para a criação de variantes de produtos com características específicas.
**Colunas:**

- **`id`**: Identificador único do atributo (Chave Primária - PK).
- **`name`**: Nome descritivo do atributo (ex: "Tamanho").
- **`data_type`**: Tipo de dado que o atributo recebe, como texto, número ou booleano.

### `variant_attribute_values`

**Descrição:** Tabela associativa que cruza a variante de um produto com seus atributos específicos e o valor correspondente (ex: Variante X tem Atributo Cor com Valor "Azul"). Essencial para modelar matrizes de produtos complexos.
**Colunas:**

- **`product_variant_id`**: Referência à variante do produto (Chave Estrangeira - FK e parte da Chave Primária Composta).
- **`attribute_id`**: Referência ao atributo aplicado (Chave Estrangeira - FK e parte da Chave Primária Composta).
- **`value`**: O valor real atribuído àquela característica para a variante específica (ex: "GG", "220V").

---

## Gestão de Clientes

### `customers`

**Descrição:** Responsável por armazenar o cadastro principal de clientes do negócio, englobando tanto pessoas físicas quanto jurídicas. Mantém os dados de contato e identificação fiscal necessários para vendas e relacionamento.
**Colunas:**

- **`id`**: Identificador único do cliente (Chave Primária - PK).
- **`person_type`**: Indicador do tipo de pessoa (física ou jurídica).
- **`legal_name`**: Nome completo ou Razão Social do cliente.
- **`trade_name`**: Nome fantasia (aplicável a pessoas jurídicas).
- **`tax_id`**: Documento de identificação fiscal principal (como CPF ou CNPJ).
- **`state_registration`**: Inscrição Estadual para fins de tributação, caso aplicável.
- **`email`**: Endereço de correio eletrônico do cliente para contato e acesso.
- **`phone`**: Número de telefone de contato do cliente.
- **`is_active`**: Indicador booleano de status da conta do cliente (ativo ou inativo).
- **`created_at`**: Data e hora em que o registro do cliente foi criado no sistema.
- **`updated_at`**: Data e hora da última alteração no cadastro do cliente.

---

## Vendas e Devoluções

### `orders`

**Descrição:** É a entidade central de vendas que representa um "Pedido". Une o cliente, o vendedor, as condições de compra, localização, descontos aplicados e resume os totais financeiros e status da operação de venda.
**Colunas:**

- **`id`**: Identificador único interno do pedido (Chave Primária - PK).
- **`order_number`**: Número oficial do pedido exibido ao cliente (ex: #120934).
- **`channel`**: Canal por onde a venda foi realizada (ex: Loja Física, E-commerce).
- **`customer_id`**: Referência ao comprador (Chave Estrangeira - FK).
- **`salesperson_id`**: Referência ao funcionário que atendeu/vendeu, se aplicável (Chave Estrangeira - FK).
- **`location_id`**: Referência à filial de origem (Chave Estrangeira - FK).
- **`status`**: Estado em que o pedido se encontra no fluxo de vida (ex: pago, faturado, enviado).
- **`subtotal`**: Soma bruta dos valores dos produtos.
- **`discount_amount`**: Montante financeiro do desconto concedido na venda como um todo.
- **`total`**: Valor financeiro líquido final que deve ser cobrado do cliente.
- **`placed_at`**: Data e hora exata de quando o cliente finalizou/colocou o pedido.
- **`created_at`**: Timestamp do registro no banco de dados.
- **`updated_at`**: Timestamp da última alteração de qualquer dado deste cabeçalho.

### `order_items`

**Descrição:** Tabela que contém os detalhes granulares de um pedido de venda, representando o "carrinho" de compras do cliente. Armazena quais variantes de produtos foram vendidas, em qual quantidade e com qual preço e carga tributária no momento da venda.
**Colunas:**

- **`id`**: Identificador único da linha do pedido (Chave Primária - PK).
- **`order_id`**: Referência ao cabeçalho do pedido (Chave Estrangeira - FK).
- **`product_variant_id`**: Referência à variante do produto comercializado (Chave Estrangeira - FK).
- **`quantity`**: Quantidade de unidades compradas.
- **`unit_price`**: Preço unitário fechado no momento da venda.
- **`icms_rate`**: Alíquota do imposto ICMS aplicada neste item.
- **`ipi_rate`**: Alíquota do imposto IPI aplicada neste item.
- **`line_total`**: Valor total da linha (quantidade multiplicada pelo preço unitário, com impostos dependendo da regra de negócio).

### `payments`

**Descrição:** Registra as transações financeiras ligadas aos pedidos de venda. Permite lidar com compras parceladas, múltiplos métodos de pagamento e monitorar o status de quitação de uma dívida de pedido.
**Colunas:**

- **`id`**: Identificador único da tentativa ou transação de pagamento (Chave Primária - PK).
- **`order_id`**: Referência ao pedido que está sendo pago (Chave Estrangeira - FK).
- **`method`**: Forma de pagamento utilizada (ex: Cartão de Crédito, PIX, Boleto).
- **`installments`**: Número de parcelas escolhidas no plano de pagamento.
- **`amount`**: Valor financeiro da transação referida.
- **`status`**: Situação da cobrança (ex: Pendente, Aprovado, Estornado).
- **`paid_at`**: Data e hora em que a confirmação de recebimento/pagamento ocorreu.
- **`created_at`**: Data de inserção do registro de tentativa/cobrança no sistema.
- **`updated_at`**: Modificação de dados de registro de pagamento.

### `fiscal_invoices`

**Descrição:** Responsável por armazenar as informações relacionadas ao faturamento legal e Notas Fiscais Eletrônicas emitidas a partir de um pedido. Guarda as chaves fiscais e metadados vitais para a contabilidade e validação na SEFAZ.
**Colunas:**

- **`id`**: Identificador único do registro fiscal no sistema (Chave Primária - PK).
- **`order_id`**: Referência ao pedido que originou esta fatura (Chave Estrangeira - FK).
- **`nfe_number`**: Número sequencial da Nota Fiscal Eletrônica.
- **`nfe_access_key`**: Chave de acesso de 44 dígitos gerada pela Receita/SEFAZ.
- **`series`**: Série da nota fiscal de faturamento.
- **`issued_at`**: Data e hora de emissão do documento fiscal.
- **`status`**: Status da nota junto ao órgão autorizador (ex: autorizada, cancelada, denegada).
- **`total_amount`**: Valor total processado nesta nota fiscal.
- **`xml_storage_uri`**: Caminho ou link no bucket/servidor onde o arquivo XML da nota está guardado.
- **`created_at`**: Timestamp da geração do registro no sistema interno.
- **`updated_at`**: Timestamp da última mudança do documento.

### `returns`

**Descrição:** Gerencia os processos de devoluções de mercadorias pelos clientes. Controla o status da devolução, o motivo, e os valores financeiros a serem reembolsados, conectando-se ao pedido original.
**Colunas:**

- **`id`**: Identificador único do processo de devolução (Chave Primária - PK).
- **`return_number`**: Número de identificação amigável ou protocolo da devolução.
- **`order_id`**: Referência ao pedido original que gerou a devolução (Chave Estrangeira - FK).
- **`customer_id`**: Referência ao cliente que está realizando a devolução (Chave Estrangeira - FK).
- **`received_at_location_id`**: Referência ao local (estoque/filial) onde a devolução foi recebida (Chave Estrangeira - FK).
- **`status`**: Estado atual do processo de devolução (ex: pendente, aprovado, concluído).
- **`reason`**: Motivo alegado pelo cliente para a devolução.
- **`total_refund_amount`**: Valor financeiro total a ser estornado ou creditado ao cliente.
- **`created_at`**: Data e hora de abertura do processo de devolução.
- **`updated_at`**: Data e hora da última atualização do status ou dados da devolução.

### `return_items`

**Descrição:** Detalha os itens individuais contidos dentro de um processo de devolução geral. Especifica exatamente quais produtos estão voltando, as quantidades, as ações tomadas e valores parciais de reembolso.
**Colunas:**

- **`id`**: Identificador único do item devolvido (Chave Primária - PK).
- **`return_id`**: Referência ao processo de devolução pai (Chave Estrangeira - FK).
- **`order_item_id`**: Referência específica à linha do pedido original (Chave Estrangeira - FK).
- **`quantity`**: Quantidade de unidades daquele item sendo devolvidas.
- **`action`**: Ação a ser tomada sobre o item (ex: estornar, trocar, descartar).
- **`exchange_variant_id`**: Em caso de troca, indica por qual nova variante o produto será substituído (Chave Estrangeira - FK).
- **`unit_refund_amount`**: Valor unitário de reembolso aprovado para este item.

---

## Produtos, Marcas e Categorias

### `products`

**Descrição:** Tabela "pai" do catálogo de itens, definindo características gerais que agrupam as variantes. Contém metadados descritivos como nome base, taxonomia (marca e categoria) e classificação fiscal (NCM).
**Colunas:**

- **`id`**: Identificador único do produto pai (Chave Primária - PK).
- **`name`**: Nome público ou de cadastro do produto.
- **`description`**: Texto de descrição, especificações gerais e detalhes do produto.
- **`brand_id`**: Referência à marca comercial do produto (Chave Estrangeira - FK).
- **`category_id`**: Referência à categoria primária à qual o produto pertence (Chave Estrangeira - FK).
- **`ncm_code`**: Nomenclatura Comum do Mercosul, usado para classificação fiscal.
- **`unit_of_measure`**: Unidade de medida do produto (ex: Unidade, Caixa, Metro, KG).
- **`is_active`**: Status booleano indicando se o produto base está ativo no catálogo.
- **`created_at`**: Timestamp de criação.
- **`updated_at`**: Timestamp da última edição.

### `product_variants`

**Descrição:** Representa a unidade transacional de um produto (SKU). Como um produto abstrato pode ter variações (cores, tamanhos), esta tabela armazena dados comerciais diretos como preço, peso, códigos de barra e impostos de cada variação específica.
**Colunas:**

- **`id`**: Identificador único da variante (Chave Primária - PK).
- **`product_id`**: Referência ao modelo principal do produto (Chave Estrangeira - FK).
- **`sku`**: Stock Keeping Unit, código único de identificação comercial da variante.
- **`barcode_ean`**: Código de barras ou código EAN utilizado no varejo.
- **`sale_price`**: Preço padrão de venda ao consumidor final.
- **`cost_price`**: Custo padrão de aquisição ou produção da variante.
- **`weight_kg`**: Peso físico do produto em quilogramas para fins logísticos.
- **`icms_rate`**: Alíquota padrão de ICMS.
- **`ipi_rate`**: Alíquota padrão de IPI.
- **`is_active`**: Indicador booleano que permite inativar a venda da variante temporariamente.
- **`created_at`**: Data de criação do registro da variante.
- **`updated_at`**: Data de atualização da variante.

### `brands`

**Descrição:** Cadastro auxiliar de marcas de produtos. Permite classificar e filtrar o catálogo de acordo com o fabricante ou a marca comercial sob a qual os itens são vendidos.
**Colunas:**

- **`id`**: Identificador único da marca (Chave Primária - PK).
- **`name`**: Nome da marca.
- **`country`**: País de origem da marca.
- **`is_active`**: Indicador se a marca ainda está ativa no sistema.
- **`created_at`**: Data e hora de criação.
- **`updated_at`**: Data e hora de atualização.

### `categories`

**Descrição:** Estrutura a árvore hierárquica taxonômica dos produtos. Suporta relacionamento consigo mesma (auto-relacionamento) para permitir a criação de categorias "pai" e subcategorias infinitas.
**Colunas:**

- **`id`**: Identificador único da categoria (Chave Primária - PK).
- **`name`**: Nome amigável da categoria (ex: Eletrônicos, Celulares).
- **`slug`**: Versão textual amigável em URL (ex: eletrônicos-e-celulares) usada para e-commerce.
- **`parent_category_id`**: Referência à categoria superior, permitindo formar subcategorias (Chave Estrangeira - FK).
- **`is_active`**: Booleano que define se a categoria está visível e utilizável.
- **`created_at`**: Timestamp da criação da categoria.
- **`updated_at`**: Timestamp de modificação.

---

## Estoque, Localizações e Movimentações

### `locations`

**Descrição:** Define os espaços físicos ou lógicos da empresa, como filiais, lojas físicas, centros de distribuição ou estoques de trânsito. Funciona como a base georreferenciada para estoques, vendas e alocação de funcionários.
**Colunas:**

- **`id`**: Identificador único do local (Chave Primária - PK).
- **`name`**: Nome da filial, loja ou depósito de armazenamento.
- **`location_type`**: Categoria de classificação operacional (ex: Loja, Armazém, etc).
- **`postal_code`**: Código postal (CEP) da unidade.
- **`street`**: Logradouro onde a localização encontra-se.
- **`number`**: Número predial do local.
- **`complement`**: Dados adicionais como Galpão, Sala, Andar.
- **`district`**: Bairro de localização da filial.
- **`city`**: Cidade de localização da filial.
- **`state`**: Estado ou UF da localização da filial.
- **`country`**: País de localização da filial.
- **`is_active`**: Indicador se a localidade ainda se encontra operante.
- **`created_at`**: Registro de criação do registro.
- **`updated_at`**: Última alteração na localidade.

### `stock_levels`

**Descrição:** Controla o saldo instantâneo de estoque de cada variante de produto em cada localização física. É vital para evitar rupturas ou excesso de estoque, mantendo também pontos de ressuprimento.
**Colunas:**

- **`product_variant_id`**: Referência à variante do produto (Chave Estrangeira - FK e parte da Chave Primária Composta).
- **`location_id`**: Referência ao local físico/estoque onde o produto está armazenado (Chave Estrangeira - FK e parte da Chave Primária Composta).
- **`quantity_on_hand`**: Quantidade de saldo físico atualmente disponível no local.
- **`reorder_point`**: Nível mínimo de estoque que, ao ser atingido, dispara o alerta de necessidade de nova compra.
- **`updated_at`**: Timestamp da última modificação do saldo.

### `stock_movements`

**Descrição:** Consiste no livro-razão (log ou histórico) de todas as movimentações de inventário (entradas e saídas). Crucial para auditorias de estoque (kardex) e rastreio, associando quem moveu, por que moveu e qual a base documental envolvida.
**Colunas:**

- **`id`**: Identificador único da transação de movimentação (Chave Primária - PK).
- **`product_variant_id`**: Referência à variante do produto movida (Chave Estrangeira - FK).
- **`location_id`**: Referência ao estoque afetado (Chave Estrangeira - FK).
- **`movement_type`**: Natureza da operação (Entrada, Saída, Transferência, Ajuste).
- **`quantity`**: Quantidade de saldo envolvida na movimentação.
- **`reference_table`**: Nome da tabela referencial que gerou o movimento (ex: order_items, goods_receipt_items).
- **`reference_id`**: ID correspondente à linha dentro da tabela base citada em reference_table.
- **`employee_id`**: Referência ao colaborador responsável pela movimentação física (Chave Estrangeira - FK).
- **`notes`**: Observações ou comentários sobre a ocorrência ou ajuste no estoque.
- **`occurred_at`**: Timestamp exato de quando o movimento se consolidou fisicamente no depósito.
- **`created_at`**: Timestamp da inserção desta linha de log de movimento no banco.

---

## Compras, Fornecedores e Recebimentos (Supply Chain)

### `suppliers`

**Descrição:** Banco de dados central das empresas fornecedoras que alimentam o estoque e provêm matéria-prima ou produtos acabados. Detém contatos, e detalhes de natureza fiscal de parcerias B2B essenciais.
**Colunas:**

- **`id`**: Identificador único do Fornecedor (Chave Primária - PK).
- **`legal_name`**: Razão social que consta em documentos fiscais de faturamento.
- **`trade_name`**: Nome fantasia ou marca popular conhecida pelo fornecedor.
- **`country`**: País residente, impactando possíveis processos de comércio exterior/importação.
- **`tax_id`**: Documento do país matriz (Ex: CNPJ).
- **`tax_id_type`**: Qualificação do tipo de documento tributário registrado.
- **`email`**: Contato para cotações e documentação financeira.
- **`phone`**: Telefone geral de atendimento à empresa corporativa.
- **`contact_name`**: Nome ou representante de conta interna que realiza atendimento preferencial das demandas.
- **`is_active`**: Define se a empresa continuará sendo visível no catálogo de fornecedores da rotina.
- **`created_at`**: Registro de sistema da criação da linha.
- **`updated_at`**: Modificação por processos na atualização da tabela.

### `product_suppliers`

**Descrição:** Tabela que mapeia a relação de qual fornecedor vende qual produto para a empresa. Guarda o código do produto na visão do fornecedor, ajudando na conversão, além de acompanhar os históricos de tempo logístico e de custos para abastecimento.
**Colunas:**

- **`product_variant_id`**: Referência à variante do produto a nível interno (Chave Estrangeira - FK e parte da Chave Primária Composta).
- **`supplier_id`**: Referência ao fornecedor que produz/revende (Chave Estrangeira - FK e parte da Chave Primária Composta).
- **`supplier_sku`**: O código do produto sob a perspectiva do fornecedor (facilita compras B2B).
- **`last_quoted_cost`**: Último preço de custo tabela do que o fornecedor informou ou vendeu este item.
- **`lead_time_days`**: Estimativa em dias desde o aceite do pedido de compra pelo fornecedor até a chegada no local do negócio.
- **`is_preferred`**: Booleano que sugere este fornecedor como a primeira opção (preferencial) ao rodar robôs ou analistas de compra por demanda de ruptura.
- **`created_at`**: Início deste vínculo entre fornecedor e produto.
- **`updated_at`**: Última alteração na condição comercial da relação.

### `purchase_orders`

**Descrição:** Cabeçalho mestre de compra, semelhante aos pedidos de clientes, só que de trás para frente. Organiza os valores que se vai pagar, dados do fornecedor de origem, onde os materiais têm de ser entregues e como está o status logístico do processo de suprimentos.
**Colunas:**

- **`id`**: Identificação central do controle dessa ordem no banco (Chave Primária - PK).
- **`po_number`**: Identificação amigável/comercial para troca de informações com parceiros fornecedores ("Purchase Order Number").
- **`supplier_id`**: Referência de qual fornecedor receberá este pedido (Chave Estrangeira - FK).
- **`buyer_id`**: Referência do colaborador ou analista de "supply chain" encarregado pela compra de fato (Chave Estrangeira - FK).
- **`destination_location_id`**: Referência do ponto logístico (armazém/loja) que requer os materiais (Chave Estrangeira - FK).
- **`status`**: Estado que pontua onde o pedido está em maturação (rascunho, pendente, emitido, recebido, faturado).
- **`currency`**: Moeda que padronizou a base do acordo da ordem comercial.
- **`subtotal`**: Soma quantitativa dos valores simples estipulados nos itens de compra.
- **`total`**: Soma ajustada com encargos, fretes e descontos das matrizes fornecedoras que dá peso ao montante final.
- **`placed_at`**: Timestamp do fechamento e envio comercial da ordem por parte dos analistas de compra.
- **`expected_delivery_at`**: Timestamp pactuado de prazo máximo de entrega pelo time do fornecedor.
- **`created_at`**: Inserção cronológica no ecossistema do banco.
- **`updated_at`**: Última alteração dentro de qualquer fase e dados deste pedido de aprovisionamento.

### `purchase_order_items`

**Descrição:** Especifica detalhadamente quais e quantos produtos a empresa quer comprar do fornecedor dentro do documento de Pedido de Compra. Contém os custos combinados no momento da negociação de abastecimento.
**Colunas:**

- **`id`**: Identificador único deste item no pedido de compra (Chave Primária - PK).
- **`purchase_order_id`**: Referência ao documento de compra mestre (Chave Estrangeira - FK).
- **`product_variant_id`**: Referência ao sku interno solicitado (Chave Estrangeira - FK).
- **`quantity_ordered`**: Quantidade de produto demandado na compra.
- **`unit_cost`**: Custo unitário negociado para aquela variante nesta ordem.
- **`line_total`**: Valor total deste item (custo unitário multiplicado pela quantidade encomendada).

### `goods_receipts`

**Descrição:** Registra o evento ou documento de logística "inbound" que consolida e formaliza a chegada das mercadorias de um pedido de compra no depósito da empresa.
**Colunas:**

- **`id`**: Identificador único do processo de recebimento (Chave Primária - PK).
- **`purchase_order_id`**: Referência ao pedido de compra que gerou a remessa de chegada (Chave Estrangeira - FK).
- **`received_by_employee_id`**: Referência ao encarregado do armazém que conferiu as mercadorias na doca (Chave Estrangeira - FK).
- **`received_at`**: Data e horário real de quando ocorreu a entrada do caminhão/material no depósito.
- **`notes`**: Registros qualitativos como quebras, avarias percebidas no descarregamento ou referências gerais.
- **`created_at`**: Timestamp do ato de criação no banco de dados da entrada de recebimento.

### `goods_receipt_items`

**Descrição:** Tabela de linha associada aos recebimentos físicos (entradas) de mercadorias no estoque. Cruza as quantidades recebidas em pátio com as que foram realmente pedidas e negociadas no fornecedor.
**Colunas:**

- **`id`**: Identificador único do registro de item recepcionado (Chave Primária - PK).
- **`goods_receipt_id`**: Referência ao protocolo mestre do recebimento logístico (Chave Estrangeira - FK).
- **`purchase_order_item_id`**: Referência à linha original solicitada no pedido de compra (Chave Estrangeira - FK).
- **`quantity_received`**: Volume que realmente chegou fisicamente durante a conferência.

---

## Câmbio (API BCB)

### `exchange_rates`

**Descrição:** Tabela alimentada pela API PTAX do Banco Central do Brasil com as cotações de compra e venda de moedas estrangeiras (USD e EUR) em relação ao Real (BRL), atualizada diariamente.
**Colunas:**

- **`id`**: Identificador único do registro (Chave Primária - PK).
- **`currency`**: Código ISO da moeda estrangeira (ex: USD, EUR).
- **`exchange_rate_buy`**: Taxa de câmbio de compra (BRL por unidade da moeda).
- **`exchange_rate_sell`**: Taxa de câmbio de venda (BRL por unidade da moeda).
- **`data_reference`**: Data de referência da cotação PTAX.
- **`created_at`**: Timestamp de inserção do registro.

---

## Colaboradores

### `employees`

**Descrição:** Mantém os dados cadastrais da equipe interna ou colaboradores da empresa. Estes podem ser vendedores, atendentes ou almoxarifes logísticos que interagem e são responsáveis por fluxos do sistema.
**Colunas:**

- **`id`**: Identificador único do funcionário (Chave Primária - PK).
- **`full_name`**: Nome completo do colaborador.
- **`cpf`**: Cadastro de Pessoa Física do colaborador no governo.
- **`email`**: Email corporativo ou para acesso ao sistema.
- **`role`**: Papel ou cargo interno desempenhado.
- **`primary_location_id`**: Referência à unidade padrão ou matriz onde o funcionário se baseia (Chave Estrangeira - FK).
- **`hire_date`**: Data referencial de contração da pessoa.
- **`termination_date`**: Data em que se encerrou o vínculo do colaborador com a empresa (caso aplicável).
- **`is_active`**: Indicador booleano que reflete se tem ou não acesso ao sistema hoje em dia.
- **`created_at`**: Data de criação do acesso interno.
- **`updated_at`**: Modificação de dados cadastrais de funcionários.

---

> **Notas:**
> - A tabela `fiscal_invoices` é extraída na camada Bronze via SQL Server, mas não possui modelo correspondente no dbt (não integra o modelo dimensional atual).
> - A tabela `exchange_rates` é proveniente da API PTAX do Banco Central (não do SQL Server), com dados incrementais de cotações USD e EUR. Está incluída no dbt (`stg_exchange_rates` → `int_exchange_rates` → `fact_purchase_order_items`).

---

## **Tamanho das tabelas**

- **order_items**: 150,321 linhas
- **stock_movements**: 117,427 linhas
- **payments**: 54,635 linhas
- **orders**: 50,000 linhas
- **fiscal_invoices**: 35,079 linhas
- **purchase_order_items**: 6,059 linhas
- **stock_levels**: 6,054 linhas
- **goods_receipt_items**: 4,733 linhas
- **addresses**: 3,998 linhas
- **variant_attribute_values**: 2,018 linhas
- **purchase_orders**: 2,000 linhas
- **customers**: 2,000 linhas
- **goods_receipts**: 1,548 linhas
- **product_suppliers**: 1,520 linhas
- **return_items**: 1,409 linhas
- **product_variants**: 1,009 linhas
- **returns**: 1,000 linhas
- **products**: 500 linhas
- **suppliers**: 25 linhas
- **employees**: 15 linhas
- **categories**: 14 linhas
- **brands**: 12 linhas
- **attributes**: 8 linhas
- **locations**: 6 linhas

---

## **Tamanho total por tabela (KB)**

- **stock_movements**: 14,792 KB
- **fiscal_invoices**: 13,320 KB
- **order_items**: 8,712 KB
- **orders**: 6,536 KB
- **payments**: 5,576 KB
- **addresses**: 712 KB
- **customers**: 520 KB
- **purchase_order_items**: 328 KB
- **returns**: 328 KB
- **stock_levels**: 328 KB
- **purchase_orders**: 264 KB
- **product_suppliers**: 264 KB
- **product_variants**: 264 KB
- **products**: 264 KB
- **goods_receipt_items**: 200 KB
- **goods_receipts**: 200 KB
- **variant_attribute_values**: 200 KB
- **return_items**: 136 KB
- **employees**: 72 KB
- **locations**: 72 KB
- **attributes**: 72 KB
- **brands**: 72 KB
- **categories**: 72 KB
- **suppliers**: 72 KB
