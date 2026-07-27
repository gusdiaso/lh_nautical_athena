# Relatório de Análise do Projeto LH Nautical

---

## 1. Apresentação da Solução

### 1.1 O Problema de Negócio

A LH Nautical, empresa do segmento náutico, operava com dados dispersos em um ERP SQL Server, sem visibilidade consolidada sobre sua operação. As principais dores identificadas foram:

- **Falta de visibilidade financeira**: impossibilidade de acompanhar faturamento real, custos de compra internacionais sem conversão padronizada para BRL, margem por produto e fluxo de pagamentos de forma integrada
- **Ruptura de estoque sem causa clara**: não era possível rastrear a origem dos problemas de estoque — se compra insuficiente, atraso de fornecedor, ou saída não registrada
- **Devoluções não diagnosticadas**: a empresa suspeitava que a maioria dos pedidos devolvidos resultava em estorno financeiro em vez de troca, mas não havia dados estruturados para confirmar essa hipótese nem entender os motivos reais

### 1.2 O Que Foi Construído

Implementamos um **Data Warehouse analítico** completo no ecossistema **Databricks**, seguindo a **Arquitetura Medalhão** (Bronze → Silver → Gold), com modelagem dimensional em **Star Schema** utilizando **dbt** para as transformações.

A solução extrai dados de **24 tabelas do ERP SQL Server** via JDBC e **cotações PTAX (USD/EUR) da API do Banco Central do Brasil**, processando-os através de etapas progressivas de qualidade:

| Etapa | O que faz | Como está materializado |
|-------|-----------|------------------------|
| **Bronze** | Cópia fiel dos dados originais | Tabelas Delta Lake no schema `bronze` |
| **Staging** | Organiza e renomeia colunas | 24 modelos ephemeral (CTE) |
| **Intermediate** | Limpa, valida e enriquece os dados | 24 tabelas no schema `silver` |
| **Marts (Gold)** | Modelo dimensional pronto para BI | 12 tabelas no schema `gold` (6 dimensões + 6 fatos) |

O projeto é orquestrado por **Databricks Asset Bundles (DAB)** com CI/CD automatizado via Bitbucket Pipelines, deploy em produção usando Service Principal, e mais de **245 testes automáticos** (209 genéricos + 36 singulares) de qualidade de dados.

---

### 1.3 Perguntas de Negócio Que a Solução Responde

#### Financeiro — 5 perguntas que agora podem ser respondidas

| # | Pergunta | Como a solução responde |
|---|----------|------------------------|
| 1 | **Quanto estamos faturando por produto, canal e localização?** | A `fact_order_items` registra cada item vendido com `gross_line_total` (valor bruto), `net_line_total` (após descontos), `channel` (canal de venda), e chaves para as dimensões de produto, cliente e localização |
| 2 | **Qual a margem bruta real de cada produto?** | A `fact_order_items` calcula `estimated_cost_of_goods_sold` (quantidade x custo padrão) e `estimated_gross_profit` (líquido - custo), permitindo enxergar rentabilidade por SKU |
| 3 | **Dos pagamentos recebidos, quanto foi aprovado vs estornado?** | A `fact_payments` separa `paid_amount` (valor aprovado) e `refunded_amount` (valor estornado), com flags `is_paid`, `is_refunded`, `is_pending` e `is_cancelled` mutuamente exclusivas |
| 4 | **Quanto estamos gastando de fato em compras internacionais?** | A `fact_purchase_order_items` converte custos em moeda estrangeira para BRL usando a cotação PTAX do dia do pedido, com `line_total_brl` e `unit_cost_brl` |
| 5 | **Qual o impacto dos impostos (ICMS/IPI) no preço final?** | A `int_order_items` calcula `icms_amount`, `ipi_amount` e `total_tax_amount` para cada item, permitindo análises de carga tributária por produto |

#### Logística e Estoque — 5 perguntas que agora podem ser respondidas

| # | Pergunta | Como a solução responde |
|---|----------|------------------------|
| 1 | **O que está causando a ruptura de estoque?** | A `fact_stock_movements` rastreia cada movimentação (entrada/saída) com `reference_table` apontando para a transação originadora — é possível identificar se o problema é falta de compra, atraso de fornecedor, ou saída não registrada |
| 2 | **Quais produtos estão abaixo do ponto de ressuprimento?** | A `int_stock_levels` fornece `quantity_on_hand`, `reorder_point` e a flag `is_critical_stock`. Quando o ERP não tem reorder_point, ele é calculado automaticamente pela demanda média dos últimos 90 dias |
| 3 | **Os fornecedores estão entregando no prazo?** | A `fact_goods_receipt_items` compara `expected_delivery_at` com `received_at`, calculando `delivery_variance_days` e acionando `is_late_receipt` para cada recebimento |
| 4 | **Qual a demanda média diária por produto em cada loja?** | A `int_stock_levels` calcula `avg_daily_demand` por produto e localização a partir do histórico de 90 dias de pedidos (excluindo cancelados) |
| 5 | **Estamos recebendo tudo que compramos ou há recebimentos parciais?** | A `fact_goods_receipt_items` monitora `quantity_ordered` vs `quantity_received`, com flags `is_fully_received` e `is_partial_receipt`, mais `remaining_quantity_after_receipt` |

#### Devoluções — 5 perguntas que agora podem ser respondidas

| # | Pergunta | Como a solução responde |
|---|----------|------------------------|
| 1 | **A maioria das devoluções vira estorno ou troca?** | A `fact_return_items` possui as flags `is_refund` e `is_exchange`, permitindo contabilizar exatamente a proporção entre as duas ações |
| 2 | **Quais motivos geram estorno e quais geram troca?** | A `int_returns` classifica os motivos em 8 grupos analíticos (`defeito_fabrica`, `avaria_transporte`, `desistencia_cliente`, `divergencia_descricao`, etc.), e a `fact_return_items` cruza com a ação tomada |
| 3 | **Qual o valor total reembolsado por motivo de devolução?** | A `fact_return_items` possui `total_line_refund_amount` por item e `return_has_refund_amount` no cabeçalho, permitindo somar valores por grupo de motivo |
| 4 | **Qual produto é mais devolvido e por qual motivo?** | A `fact_return_items` conecta o produto devolvido (`sk_returned_product`) à `dim_products`, permitindo análises por SKU, marca e categoria |
| 5 | **Quando há troca, para qual produto o cliente está migrando?** | A `fact_return_items` registra `sk_exchange_product` (produto de troca) quando `is_exchange = true`, permitindo rastrear padrões de substituição |

---

## 2. Fluxo de Dados — Da Fonte ao Modelo Final

### 2.1 Visão Geral

```
SQL Server (ERP - 24 tabelas)          API PTAX (BCB - USD/EUR)
       │                                        │
       ▼ JDBC (full load)                       ▼ HTTP (incremental)
┌─────────────────────────────┐    ┌─────────────────────────────┐
│         BRONZE              │    │      exchange_rates         │
│  24 tabelas Delta Lake      │    │     Delta Lake              │
└──────────┬──────────────────┘    └──────────────┬──────────────┘
           │                                      │
           └──────────────┬───────────────────────┘
                          ▼
              ┌──────────────────────────┐
              │    STAGING (24 views)    │
              │   └── schema: silver     │
              │   Organiza, renomeia     │
              │   e tipa os dados        │
              └──────────┬───────────────┘
                         ▼
              ┌──────────────────────────┐
              │  INTERMEDIATE (24 tables)│
              │   └── schema: silver     │
              │   Deduplica, padroniza,  │
              │   enriquece e valida     │
              └──────────┬───────────────┘
                         ▼
              ┌──────────────────────────┐
              │  MARTS (12 tables - gold)│
              │   6 Dimensões + 6 Fatos  │
              │   └── schema: gold       │
              │   Pronto para BI         │
              └──────────────────────────┘
```

---

### 2.2 Camada Bronze — A Chegada dos Dados

**Origem: SQL Server (ERP)**

Extraímos 24 tabelas via JDBC com carga completa (full overwrite). Para tabelas de evento, aplicamos um filtro temporal na própria query JDBC:

- **Tabelas de evento** (pedidos, pagamentos, movimentos de estoque): filtradas por `CAST(data_do_evento AS DATE) <= GETDATE()`, ou seja, apenas registros até a data atual — registros futuros são ignorados e serão capturados automaticamente quando a data for alcançada
- **Tabelas filhas** (itens do pedido, itens de devolução, etc.): filtradas pela existência do registro pai, garantindo que nunca cheguem dados órfãos
- **Tabelas cadastrais** (clientes, produtos, fornecedores): extraídas integralmente

Duas colunas de auditoria são adicionadas em cada tabela: `_ingested_at` (timestamp da extração) e `_source_path` (origem dos dados).

**Origem: API PTAX (Banco Central)**

Extraímos cotações de compra e venda para USD e EUR de forma incremental (merge/upsert), com retry automático em caso de falha de conexão (3 tentativas com backoff exponencial).

---

### 2.3 Camada Staging — A Organização

A camada Staging é a "portaria" dos dados. Ela não inventa nada, só organiza:

| Operação | O que faz | Exemplo |
|----------|-----------|---------|
| **Renomear** | Traduz nomes de colunas para inglês padronizado em snake_case | `id` → `customer_id`, `nome` → `legal_name` |
| **Tipar** | Garante que cada coluna tenha o tipo correto | Data como DATE, dinheiro como DECIMAL |
| **Filtrar** | Remove colunas de controle que só interessam ao sistema | `_ingested_at`, `_source_path` |

**Não aplicamos nenhuma regra de negócio nesta camada.** Os modelos são `ephemeral` (não materializados) — o SQL é injetado como CTE nos modelos Intermediate, servindo como um "contrato público" e estável.

---

### 2.4 Camada Intermediate — A Limpeza e Validação

A camada Intermediate é onde os dados realmente ganham confiança. Cada um dos 24 modelos (mapeando 23 tabelas fonte + `exchange_rates`) aplica:

**Transformações universais (presentes em TODOS os modelos):**

| Regra | O que faz |
|-------|-----------|
| **Filtro de PK nula** | Remove registros sem identificador (`WHERE id IS NOT NULL`) |
| **Deduplicação** | Usa `ROW_NUMBER()` com `PARTITION BY id` para manter apenas um registro por chave |
| **Padronização de texto** | Aplica `LOWER(TRIM())` em campos como status, canal, método de pagamento, moeda |
| **Tratamento de nulos** | `COALESCE()` para valores esperados, `NULLIF()` para strings vazias |

**Transformações específicas por domínio:**

**Produtos** — Corrigimos ruídos do cadastro do ERP com regras validadas pelo cliente:
- Nomes inválidos como `'tbd'` e `'asdf'` são mapeados para nomes reais baseados na descrição
- Descrições faltantes são preenchidas com texto padronizado (ex: nomes começando com "GPS Plotter" recebem descrição adequada)
- Categorias são corrigidas por palavra-chave da descrição (ex: descrições começando com "motor" → categoria 4)

**Produtos Variantes** — Calculamos métricas comerciais:
- `gross_margin_amount` = preço de venda - preço de custo
- `gross_margin_percentage` = margem / preço de venda (com proteção contra divisão por zero)
- `total_tax_rate` = ICMS + IPI
- Flag `is_profitable` = preço de venda > preço de custo

**Pedidos de Compra com Câmbio** — Regra de negócio acordada com o cliente:
- Quando `expected_delivery_at` é nulo, assumimos `placed_at + 30 dias` (prazo padrão contratual)
- Buscamos a taxa de câmbio do dia do pedido usando intervalos de validade entre cotações (via `LEAD()`), garantindo que pedidos em fins de semana ou feriados usem a cotação do último dia útil anterior
- Calculamos `total_brl`: se moeda for BRL, mantém original; senão, converte pela cotação

**Itens de Pedido** — Calculamos impostos:
- `icms_amount` = valor bruto da linha × alíquota ICMS / 100
- `ipi_amount` = valor bruto da linha × alíquota IPI / 100
- `total_with_taxes` = valor bruto × (1 + soma das alíquotas / 100)

**Devoluções** — Classificação de motivos acordada com o cliente:

| Grupo | Como identifica | Exemplo de motivo original |
|-------|-----------------|---------------------------|
| `nao_informado` | Motivo nulo, vazio ou '?' | `NULL`, `'-'` |
| `compra_duplicada` | Contém "duplicada" | "Compra duplicada acidental" |
| `desistencia_cliente` | Contém "desist" | "Desistência do cliente" |
| `divergencia_descricao` | Contém "descri" ou "corresponde" | "Produto não corresponde à descrição" |
| `avaria_transporte` | Contém "avariado" ou "transporte" | "Produto chegou avariado pelo transporte" |
| `defeito_fabrica` | Contém "defeito" | "Defeito de fábrica identificado" |
| `tamanho_cor_incorretos` | Contém "tamanho" ou "cor" | "Tamanho incorreto solicitado" |
| `outros` | Demais casos | |

**Itens de Devolução** — Cálculos e flags:
- `total_line_refund_amount` = quantidade × valor unitário de reembolso (apenas para ações `refund`)
- `is_exchange` = `action = 'exchange'`
- `is_refund` = `action = 'refund'`

**Níveis de Estoque** — Métricas preditivas acordadas com o cliente:
- `avg_daily_demand` = soma das quantidades vendidas nos últimos 90 dias / 90 (excluindo pedidos cancelados)
- `reorder_point` calculado = `ceil(demanda_média × lead_time)`, com fallback de 7 dias quando não há lead_time cadastrado
- Flag `is_critical_stock` = `quantity_on_hand <= 0 OR quantity_on_hand < reorder_point`

**Movimentações de Estoque** — Classificação de direção:
- `purchase_in` / `return_in` → 'entrada'
- `sale_out` / `return_out` → 'saida'
- Identificação de movimentações de migração legada (notas contendo "opening balance" + "system migration")

**Itens de Recebimento** — Solução acordada com o cliente:
- A tabela fonte não possui coluna de quantidade recebida
- `quantity_received` é calculado como `line_total / unit_cost` dos purchase_order_items

**Endereços** — Limpeza:
- CEP: remoção de caracteres não numéricos
- País: padronização (`'Brasil'`, `'BRA'`, `'BR'` → `'Brasil'`)

---

### 2.5 Camada Marts — O Modelo Dimensional (Gold)

A camada final organiza os dados em **6 dimensões** (tabelas descritivas) e **6 fatos** (tabelas de métricas), prontas para consumo em ferramentas de BI.

#### As 6 Dimensões

| Dimensão | O que contém | Para que serve |
|----------|-------------|----------------|
| `dim_date` | Calendário com dia, mês, trimestre, semestre, ano, flags de fim de semana e alta temporada náutica | Qualquer análise temporal — vendas por mês, devoluções por trimestre, etc. |
| `dim_customers` | Dados do cliente + endereço selecionado deterministicamente (prioriza endereço principal) | Quem comprou, quem devolveu, perfil do cliente |
| `dim_products` | Variante + produto + marca + categoria + margem bruta + impostos | Qual produto vendeu, qual foi trocado, rentabilidade |
| `dim_employees` | Funcionários + membros técnicos para venda sem vendedor ou compra sem comprador | Quem vendeu, quem comprou, quem recebeu |
| `dim_locations` | Lojas, armazéns e centros de distribuição com endereço completo | Onde vendeu, onde tem estoque, onde recebeu |
| `dim_suppliers` | Fornecedores com dados fiscais e de contato | De quem compramos, lead time, preferência |

Todas as dimensões possuem um **membro técnico** (ex: "Cliente não informado", "Produto não informado") para preservar linhas em consultas com `LEFT JOIN`.

#### As 6 Fatos

| Fato | Grão | O que registra | Tabelas envolvidas |
|------|------|---------------|-------------------|
| `fact_order_items` | 1 linha por item de pedido | Valor bruto, descontos alocados, ICMS, IPI, custo estimado, lucro bruto, flags de cancelamento | `int_order_items` + `int_orders` + dimensões |
| `fact_payments` | 1 linha por transação | Valor aprovado vs estornado, parcelas, método, flags por status | `int_payments` + `int_orders` + dimensões |
| `fact_purchase_order_items` | 1 linha por item de compra | Custos em moeda original + BRL, flag de atraso na entrega | `int_purchase_order_items` + `int_purchase_orders` + dimensões |
| `fact_goods_receipt_items` | 1 linha por item recebido | Qtd pedida vs recebida, variação de dias, flag de atraso, recebimento parcial | `int_goods_receipt_items` + `int_goods_receipts` + `int_purchase_orders` + dimensões |
| `fact_stock_movements` | 1 linha por movimentação | Tipo, direção, quantidade, referência à transação originadora | `int_stock_movements` + dimensões |
| `fact_return_items` | 1 linha por item devolvido | Produto devolvido vs produto de troca, valor reembolsado, motivo agrupado, flags exchange/refund | `int_return_items` + `int_returns` + `int_order_items` + dimensões |

**Destaques de modelagem:**

- **Desconto alocado** em `fact_order_items`: o desconto do cabeçalho do pedido é rateado proporcionalmente ao peso de cada item no total do pedido
- **Conversão cambial controlada**: valores em BRL permanecem nulos quando a cotação não está disponível (nunca assumimos zero ou 1 — decisão do cliente)
- **Produto de troca ausente**: quando a ação é `refund`, o campo `sk_exchange_product` fica nulo intencionalmente (a ausência é um dado válido, não um erro)

---

### 2.6 Saneamento e Regras de Negócio

O saneamento dos dados acontece majoritariamente na camada **Intermediate**, onde identificamos e corrigimos problemas estruturais do ERP de origem. As regras foram validadas com o cliente caso a caso.

#### Problemas Encontrados e Soluções

| Problema | Origem | Solução |
|----------|--------|---------|
| **Nulos e duplicatas** | ERP permite PK nula e registros duplicados | `WHERE pk IS NOT NULL` + `ROW_NUMBER()` em todos os modelos Intermediate |
| **Texto inconsistente** | Status, canais e moedas em caixa alta/baixa misturada | `LOWER(TRIM())` padroniza todos os campos de texto categórico |
| **Nomes de produto inválidos** | Cadastro livre com valores como `'tbd'` e `'asdf'` | Mapeamento por palavra-chave da descrição para o nome real |
| **Categoria errada** | Categoria do produto não refletia o tipo real | Correção por palavra-chave na descrição (ex: "motor" → categoria 4) |
| **Descrição de produto nula** | Descrição não era obrigatória no cadastro | Preenchimento automático baseado no padrão do nome |
| **CEP sem formatação** | Caracteres especiais, espaços e hífens inconsistentes | Macro `clean_cep`: remove não-dígitos e formata como `XXXXX-XXX` |
| **País sem padronização** | `'Brasil'`, `'BRA'`, `'BR'` coexistindo | Normalização para `'Brasil'` via `INITCAP()` e mapeamento de siglas |
| **Data de entrega nula** | Pedido de compra sem prazo contratado | Assume `placed_at + 30 dias` (prazo contratual padrão) |
| **Quantidade recebida inexistente** | ERP não armazena qtd em recebimentos | Calculada como `line_total / unit_cost` dos itens do pedido de compra |
| **Motivo de devolução livre** | Texto sem padronização, cada operador escreve de um jeito | Classificação em 8 grupos por palavra-chave (defeito, avaria, desistência, etc.) |
| **Registros com data futura** | Pedidos e movimentos agendados no ERP | Filtro `GETDATE()` na ingestão JDBC — dados futuros entram quando a data chega |
| **quantity_on_hand = 1.00 predominante** | ~99% dos registros com valor exato 1.00 — indício de placeholder ou migração incompleta | Investigar carga inicial no ERP |

#### Melhoria Aplicada: `is_critical_stock`

A flag `is_out_of_stock` foi substituída por `is_critical_stock` no modelo `int_stock_levels`.

**Antes:**
```sql
coalesce(quantity_on_hand <= 0, false) as is_out_of_stock
```

**Depois:**
```sql
coalesce(quantity_on_hand <= 0 or quantity_on_hand < reorder_point, false) as is_critical_stock
```

**O que mudou:** a flag agora considera não apenas estoque zerado/negativo, mas também produtos com saldo **abaixo do ponto de reposição** (`reorder_point`). Isso garante que itens prestes a rupturar sejam sinalizados, não apenas os já em ruptura total.

**Teste atualizado:** O arquivo `int_stock_levels_out_of_stock_flag.sql` foi substituído por `int_stock_levels_critical_stock_flag.sql`, validando a consistência da nova lógica:
```sql
where
    ((quantity_on_hand <= 0 or quantity_on_hand < reorder_point) and is_critical_stock = false)
    or
    (quantity_on_hand > 0 and quantity_on_hand >= reorder_point and is_critical_stock = true)
```

#### Regras de Negócio Aplicadas

**Financeiras:**
- ICMS e IPI calculados como alíquota × valor bruto da linha
- Margem bruta = (preço de venda − preço de custo) / preço de venda, com proteção contra divisão por zero
- Desconto do pedido rateado proporcionalmente entre os itens
- Conversão cambial: valores em moeda estrangeira convertidos pela cotação PTAX do dia; sem cotação, mantém nulo

**Logísticas:**
- Ponto de ressuprimento (reorder point): usa o cadastrado no ERP; quando ausente, calcula como `ceil(demanda_média_90dias × lead_time)` com fallback de 7 dias
- Direção de estoque: `purchase_in` / `return_in` → entrada; `sale_out` / `return_out` → saída
- Migração legada detectada por palavras-chave nas notas ("opening balance" + "system migration")

**Devoluções:**
- Ação `refund` → `is_refund = true`, `sk_exchange_product = null` (ausência intencional)
- Ação `exchange` → `is_exchange = true`, `sk_exchange_product` aponta para o produto de troca
- Valor reembolsado calculado apenas para ações `refund`

**Cadastrais:**
- Toda dimensão possui membro técnico para "não informado" — nenhuma linha da fato se perde em `LEFT JOIN`
- Funcionário de venda: quando nulo em canal e-commerce, assume membro "Sistema E-commerce"; senão, "Não informado"

---

## 3. Justificativa das Principais Decisões Técnicas

### 3.1 Por Que Arquitetura Medalhão?

**Decisão:** Separar os dados em Bronze → Silver → Gold.

**Motivo:** Cada camada tem uma responsabilidade clara e testável:
- **Bronze imutável**: preserva os dados originais para auditoria e reprocessamento — nunca alteramos a fonte
- **Staging em view**: criamos 24 views que são contratos públicos e estáveis. São leves (não ocupam armazenamento) e rápidas de atualizar
- **Intermediate em table**: materializamos as 24 tabelas porque essa camada executa joins, cálculos e validações pesadas — materializar evita reprocessamento a cada consulta
- **Gold em table**: o ponto final de consumo precisa ter performance para BI

### 3.2 Por Que dbt?

**Decisão:** dbt com materializações diferentes por camada, testes nativos e singulares.

**Motivo:**
- **Ordem automática**: o dbt descobre a ordem de execução correta através das referências (`ref()`) entre modelos — não precisamos gerenciar manualmente
- **Testes embutidos**: `not_null`, `unique`, `relationships`, `accepted_values` são configurados em YAML, sem código customizado
- **Testes singulares**: regras de negócio complexas são expressas em SQL puro e executadas como parte do pipeline — se o teste falha, o pipeline para
- **Documentação automática**: `dbt docs generate` produz um site navegável com linhagem dos dados e descrições de colunas

### 3.3 Por Que Chaves Substitutas (Surrogate Keys)?

**Decisão:** Macro `sk_from_keys` que gera chaves `sk_*` via `MD5(CONCAT_WS('||', prefixo, id))`.

**Motivo:** Precisávamos de chaves que:
- Fossem **consistentes** entre recargas (diferente de `ROW_NUMBER()` que muda a cada execução)
- Suportassem **membros técnicos**: valores `-1`, `-2`, `-3` geram hashes previsíveis para registros de "não informado"
- Fossem **eficientes**: MD5 é rápido e deterministico

### 3.4 Por Que Membros Técnicos em Todas as Dimensões?

**Decisão:** Cada dimensão possui um registro técnico para "não informado".

**Motivo:** Quando uma fato faz `LEFT JOIN` com uma dimensão e não encontra correspondência, a linha simplesmente desaparece. Com o membro técnico, garantimos que **nenhuma linha da fato se perde** — o analista vê claramente "Cliente não informado" em vez de perder o registro. Isso é fundamental para:
- Vendas sem vendedor vinculado (ex: e-commerce)
- Compras sem comprador registrado
- Produtos sem categoria definida

### 3.5 Por Que Staging em View e o Resto em Table?

**Decisão:** Materialização mista.

**Motivo:**
- **Staging (view)**: a camada mais leve — só renomeia colunas. Não faz sentido materializar algo tão simples
- **Intermediate (table)**: faz cálculos, joins, deduplicações — materializar evita que esses custos sejam repetidos a cada consulta
- **Marts (table)**: é o ponto de consumo. Ferramentas de BI consultam essas tabelas repetidamente — precisam ser rápidas

### 3.6 Por Que Filtramos Registros Futuros na Ingestão?

**Decisão:** As queries JDBC aplicam `CAST(data_do_evento AS DATE) <= GETDATE()`.

**Motivo:** O ERP continha pedidos e movimentações com data futura (ex: pedidos agendados). Se esses registros fossem para a Bronze sem tratamento, quebrariam agregações temporais e a lógica de "atraso" nas fatos. A decisão foi filtrar na origem (SQL Server) em vez de tratar no dbt, garantindo que a Bronze já chegue limpa. Quando a data futura for alcançada, a próxima extração capturará o registro automaticamente.

### 3.7 Por Que Usamos Intervalo de Validade para Câmbio?

**Decisão:** Usar `LEAD()` para criar janelas de validade entre cotações PTAX e fazer JOIN com a data da transação.

**Motivo:** A API do Banco Central não publica cotações em fins de semana e feriados. Se um pedido de compra é feito em um sábado, precisamos usar a cotação da sexta-feira anterior. Com o intervalo de validade (via `LEAD()`), criamos faixas de datas onde cada cotação é válida até a próxima disponível — qualquer data encontra a cotação correta sem precisar de buscas complexas.

### 3.8 Por Que Mantemos Nulos em Conversões Cambiais?

**Decisão:** Quando a taxa de câmbio não está disponível, os valores em BRL permanecem nulos.

**Motivo:** Decisão do cliente. Assumir zero ou 1 para uma cotação ausente criaria custos falsos — uma compra internacional sem cotação viraria "grátis" (se zero) ou com taxa errada. Nulo é explícito, alerta o analista, e não mascara o problema.

### 3.9 Por Que 245+ Testes Automáticos?

**Decisão:** Testes genéricos nos YAMLs + testes singulares em SQL para regras de negócio.

**Motivo:** Qualquer pipeline de dados é tão confiável quanto seus testes. Organizamos os testes por camada no pipeline:
```
deps → intermediate_run → intermediate_test → marts_run → marts_test
```
A camada staging é `ephemeral` (CTE), portanto seus modelos são compilados junto com o intermediate. Se a intermediate falha, não chega ao gold. Isso garante que **dados com problema nunca chegam à camada de consumo**.

Exemplos de regras protegidas por testes:
- Um pagamento `approved` deve ter `paid_amount = payment_amount` e `refunded_amount = 0`
- Se a ação é `refund`, o produto de troca deve ser nulo; se é `exchange`, o produto de troca deve existir
- A flag `is_critical_stock` deve ser `true` quando `quantity_on_hand <= 0` ou `quantity_on_hand < reorder_point`
- Pedidos em moeda estrangeira sem cotação disponível disparam alerta

### 3.10 Por Que Orquestração com DAB + CI/CD?

**Decisão:** Jobs do Databricks declarados como código (DAB) + Bitbucket Pipelines para deploy automático.

**Motivo:** Todo o pipeline é executado em 3 jobs coordenados:
1. `extract_lh_nautical` — extrai 24 tabelas do SQL Server (paralelo)
2. `extract_exchange_rates` — extrai cotações PTAX
3. `dbt_transform` — executa staging → intermediate → marts com testes entre cada etapa

O job `orchestrator_transform` coordena os 3, executando as extrações em paralelo e a transformação apenas após ambas concluírem. O deploy em produção é automatizado via Bitbucket Pipelines usando Service Principal, sem depender de token de usuário.

---

## 4. Ajustes Acordados com o Cliente

Todas as regras abaixo foram discutidas e aprovadas pelo cliente durante o desenvolvimento:

| Ajuste | O problema | A solução | Onde |
|--------|-----------|-----------|------|
| **Nomes de produtos inválidos** | ERP permitia `'tbd'` e `'asdf'` como nome | Mapeamento para nomes reais baseado na descrição | `int_products.sql` |
| **Descrições de produtos nulas** | Produtos sem descrição no cadastro | Preenchimento automático por padrão do nome | `int_products.sql` |
| **Categoria incorreta** | Categoria não refletia o tipo do produto | Correção por palavra-chave da descrição | `int_products.sql` |
| **Quantidade recebida ausente** | ERP não armazena qtd em goods_receipt_items | Derivado de `line_total / unit_cost` | `int_goods_receipt_items.sql` |
| **Data de entrega nula** | Pedidos de compra sem prazo contratado | Assume `placed_at + 30 dias` | `int_purchase_orders.sql` |
| **Ponto de ressuprimento não cadastrado** | Produtos sem reorder_point no ERP | Calculado por demanda média × lead time | `int_stock_levels.sql` |
| **Motivos de devolução inconsistentes** | Texto livre e sem padronização | Classificação em 8 grupos por palavra-chave | `int_returns.sql` |
| **Conversão cambial sem cotação** | Pedido em moeda estrangeira sem taxa disponível | Mantém nulo em vez de assumir valor falso | `fact_purchase_order_items.sql` |
| **Registros com data futura** | ERP continha pedidos e movimentos futuros | Filtro na ingestão por `GETDATE()` | `extract_lh_nautical.py` |

---

## 5. Qualidade e Governança

### Cobertura de Testes

| Tipo | Quantidade | O que validam |
|------|-----------|--------------|
| Testes genéricos (YAML) | ~209 | `not_null`, `unique`, `relationships`, `accepted_values` |
| Testes singulares (SQL) | 36 | Regras de negócio específicas (consistência financeira, lógica de estoque, integridade de devoluções) |

### Pipeline com Barreiras de Qualidade

```
deps → staging_run → staging_test → intermediate_run → intermediate_test → marts_run → marts_test
```

Cada camada só avança se a anterior passar em todos os testes.

### CI/CD

- Deploy automático via Bitbucket Pipelines ao fazer push na `main`
- Produção autenticada por Service Principal (sem token pessoal)
- Permissões granulares: grupo `dev` gerencia, grupo `prod` apenas visualiza

---

## 6. Conclusão

O projeto LH Nautical transformou dados dispersos de um ERP em um **Data Warehouse analítico completo**, capaz de dar visibilidade financeira, logística e de pós-venda para a empresa.

**O que a empresa ganhou:**

| Área | Antes | Agora |
|------|-------|-------|
| **Financeiro** | Sem visão de margem por produto, custo real de importação ou fluxo de pagamentos consolidado | Faturamento, margem bruta, custos com câmbio e pagamentos aprovados vs estornados em uma única consulta |
| **Logística** | Ruptura de estoque inexplicável, sem rastreabilidade | Saldo atual, demanda média, ponto de ressuprimento, lead time de fornecedor, atrasos por pedido |
| **Devoluções** | "Sabemos que a maioria vira estorno, mas não sabemos por quê" | Motivo agrupado, ação tomada, valor envolvido, produto devolvido vs produto de troca |

Todas as regras de negócio foram construídas **em parceria com o cliente**, que validou cada ajuste para garantir que os dados refletissem a realidade operacional mesmo diante das limitações do ERP de origem.

### Para Saber Mais

- `docs/star_schema.md` — modelo dimensional completo
- `docs/orquestracao_transform.md` — orquestração dos jobs
- `docs/dictionary.md` — dicionário das 24 tabelas fonte ERP + exchange_rates (API BCB)
- `docs/marts_tests.md` — estratégia de testes

---

## Apêndice A — Estrutura Sugerida para Apresentação (Slides)

### Slide 1 — Capa

**LH Nautical — Data Warehouse Analítico**

> Data Warehouse analítico em Databricks + dbt com modelagem dimensional para dar visibilidade financeira, logística e de pós-venda.

### Slide 2 — O Problema

**3 dores de negócio que motivaram o projeto**

| Área | Problema |
|------|----------|
| Financeiro | Sem visibilidade de faturamento real, margem por produto ou custo de importação |
| Logística | Ruptura de estoque sem rastreabilidade de causa |
| Devoluções | Suspeita de que a maioria vira estorno, sem dados para confirmar |

### Slide 3 — A Solução em 1 Minuto

**Arquitetura Medalhão + Star Schema + dbt + 245 testes**

```
SQL Server ──► Bronze ──► Staging ──► Intermediate ──► Marts (Gold)
(24 tabelas)    (cópia)   (24 views)   (24 tables)      6 dims + 6 fatos
                                                          └── Pronto para BI
```

### Slide 4 — Fluxo de Dados — Visão Detalhada

**Slide principal — mostra o diagrama de arquitetura**

```
┌─────────────────────────────────────────────────────────────────────┐
│                      INGESTÃO (Python/DAB)                          │
│  SQL Server (24 tabelas) ──full load──► Bronze (Delta)              │
│  API PTAX BCB (USD/EUR) ──incremental──► exchange_rates            │
└───────────────────────────────┬─────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│               TRANSFORMAÇÃO (dbt)                                   │
│                                                                     │
│  Staging (24 ephemeral)                                           │
│  ├── Renomeia colunas para inglês snake_case                       │
│  ├── Tipa dados corretamente                                       │
│  └── Remove colunas de auditoria                                   │
│         ▼                                                          │
│  Intermediate (24 tables — silver)                                 │
│  ├── Filtra PK nula, deduplica com ROW_NUMBER                      │
│  ├── Padroniza texto (LOWER + TRIM)                                │
│  ├── Enriquece: impostos, margem, câmbio, demanda média            │
│  └── Classifica: motivo de devolução, direção de estoque           │
│         ▼                                                          │
│  Marts (12 tables — gold)                                          │
│  ├── 6 dimensões: date, customer, product, employee, location,     │
│  │                 supplier                                        │
│  └── 6 fatos: order_items, payments, purchase_order_items,         │
│               goods_receipt_items, stock_movements, return_items   │
└─────────────────────────────────────────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   TESTES E GOVERNANÇA                               │
│  209+ testes genéricos (not_null, unique, relationships, values)   │
│  + 36 testes singulares (regras de negócio em SQL)                 │
│  Pipeline: deps → int_run → int_test → marts_run → marts_test      │
│  CI/CD: Bitbucket Pipelines → deploy automático na main            │
└─────────────────────────────────────────────────────────────────────┘
```

### Slide 5 — As 3 Principais Decisões Técnicas

| Decisão | Alternativa rejeitada | Por quê |
|---------|----------------------|---------|
| **Staging em ephemeral** (não table) | Materializar staging economizaria tempo | Staging só renomeia colunas — ephemeral é mais leve (não ocupa storage, vira CTE) e atualiza automaticamente |
| **Intermediate em table** (não view) | Manter como view economizaria storage | Intermediate faz joins pesados, cálculos e dedup — materializar evita reprocessar a cada consulta |
| **Chave substituta MD5** (não ROW_NUMBER) | ROW_NUMBER é mais simples | ROW_NUMBER muda a cada execução — MD5 é deterministico e suporta membros técnicos |

### Slide 6 — Modelo Dimensional (Star Schema)

**Tabela resumo das 6 dimensões e 6 fatos**

#### Dimensões

| Dimensão | Grão | Membro técnico |
|----------|------|----------------|
| `dim_customers` | 1 por cliente | "Cliente não informado" |
| `dim_products` | 1 por variante (SKU) | "Produto não informado" |
| `dim_employees` | 1 por funcionário | Migração, E-commerce, "Não informado" |
| `dim_locations` | 1 por localização física | "Localização não informada" |
| `dim_suppliers` | 1 por fornecedor | "Fornecedor não informado" |
| `dim_date` | 1 por dia | — |

#### Fatos

| Fato | Grão | O que responde |
|------|------|----------------|
| `fact_order_items` | 1 por item de pedido | Faturamento, margem, impostos por SKU |
| `fact_payments` | 1 por transação | Aprovado vs estornado, método, parcelas |
| `fact_purchase_order_items` | 1 por item de compra | Custo real em BRL, atraso |
| `fact_goods_receipt_items` | 1 por item recebido | Qtd pedida vs recebida, prazo |
| `fact_stock_movements` | 1 por movimentação | Origem da ruptura, direção |
| `fact_return_items` | 1 por item devolvido | Refund vs exchange, motivo, valores |

### Slide 7 — Barreiras de Qualidade

**Nenhum dado ruim chega ao BI**

```
deps → staging_run → staging_test → int_run → int_test → marts_run → marts_test
       └── se falha  ──┘             └── se falha ──┘         └── se falha ──┘
```

- **209 testes genéricos**: checam nulidade, unicidade, integridade referencial e valores válidos
- **36 testes singulares**: regras de negócio em SQL puro (ex: pagamento aprovado tem valor correto, refund não tem produto de troca)
- **CI/CD**: deploy automático ao push na `main` via Bitbucket Pipelines

### Slide 8 — O Que a Empresa Ganhou

| Área | Antes | Agora |
|------|-------|-------|
| **Financeiro** | Sem margem por produto, custo de importação ou fluxo de pagamento | `fact_order_items` + `fact_payments` + `fact_purchase_order_items` respondem tudo |
| **Logística** | Ruptura sem rastreabilidade | `fact_stock_movements` + `int_stock_levels` rastreiam causa raiz |
| **Devoluções** | "Sabemos que vira estorno, mas não por quê" | `fact_return_items` com motivo agrupado, ação, valor, produto de troca |

### Slide 9 — Perguntas e Respostas

- Código fonte: Bitbucket (link)
- Documentação interativa: `dbt docs generate` (link)
- Contato: time de dados (email)
