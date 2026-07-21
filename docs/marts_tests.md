# Estratégia de Testes da Camada Marts

## Objetivo

Esta documentação descreve a estratégia de testes atualmente implementada para a camada `marts` do projeto dbt `lh_nautical`.

O foco é registrar, com precisão técnica, como a camada analítica está protegida contra falhas de modelagem, inconsistências de relacionamento, problemas de qualidade de dados e regressões em regras de negócio. A documentação serve como referência oficial para onboarding, auditoria, code review e manutenção evolutiva.

O escopo cobre exclusivamente o que está implementado no repositório neste momento. Não há proposição de novos testes nesta documentação.

---

## Visão Geral da Arquitetura

A camada `marts` é composta por 12 modelos, todos materializados como `table` no schema `gold`, conforme definido em [dbt_project.yml](../../dbt_project.yml).

A estratégia de validação está distribuída em dois níveis:

- `Generic Tests` no arquivo [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml), cobrindo principalmente chaves, nulidade, domínios permitidos e integridade referencial.
- `Singular Tests` em [src/dbt/tests](../../src/dbt/tests), cobrindo regras de negócio e consistência de cálculos que dependem de múltiplas colunas ou de expressões derivadas.

Não há `Unit Tests` implementados para a camada `marts`.

Também não foi identificado uso de `dbt-expectations` no projeto. O `requirements.txt` contém `dbt-core` e `dbt-databricks`, mas não há dependência declarada para esse pacote, nem arquivo `packages.yml` no repositório.

### Convenções adotadas

- Chaves substitutas e naturais críticas recebem `not_null` e, quando aplicável, `unique`.
- Fatos recebem `relationships` para dimensões conformadas e, em alguns casos, para fatos de origem quando a regra de negócio exige rastreabilidade adicional.
- Flags booleanas são tratadas com `accepted_values` `[true, false]`.
- Domínios fechados de status e classificações recebem `accepted_values` explícitos.
- Regras aritméticas e cronológicas complexas ficam nos testes singulares.
- Os testes seguem a sintaxe `data_tests` com `arguments`, alinhada ao padrão de dbt 1.11+.

### Distribuição da cobertura

- Modelos: 12
- Generic Tests: 294
- Singular Tests: 8
- Unit Tests: 0
- Total de testes na camada `marts`: 302

---

## Cobertura por Modelo

# dim_date

## Objetivo

Dimensão calendário com uma linha por dia, usada como dimensão compartilhada pelos fatos da camada `marts`. O modelo gera atributos de data, decomposição temporal e indicadores auxiliares para análises de calendário.

## Regras de Negócio

- A dimensão deve ter uma linha por dia entre a menor data operacional encontrada e um horizonte adicional de 365 dias.
- `sk_date` é a chave substituta em formato `YYYYMMDD`.
- `full_date` deve ser única para garantir o grão diário.
- Os atributos de calendário devem refletir uma decomposição consistente da data.
- Os valores de dia da semana, mês, trimestre e semestre precisam permanecer dentro de domínios fechados.
- `is_weekend` e `is_high_season` são flags booleanas derivadas da própria data.

## Colunas Críticas

| Coluna | Descrição | Criticidade |
|---|---|---|
| `sk_date` | Chave substituta da data. | Alta |
| `full_date` | Data completa em nível diário. | Alta |
| `day_of_week_number` | Número do dia da semana. | Média |
| `month_number` | Número do mês. | Média |
| `quarter_number` | Número do trimestre. | Média |
| `semester_number` | Número do semestre. | Média |
| `is_weekend` | Indicador de fim de semana. | Média |
| `is_high_season` | Indicador de alta temporada náutica. | Média |

## Testes Implementados

### Generic Tests

| Nome do teste | Tipo | Objetivo | Regra protegida | Colunas envolvidas | Risco mitigado | Arquivo |
|---|---|---|---|---|---|---|
| `not_null + unique` em chave diária | Generic | Garantir unicidade do grão diário | Cada data aparece uma única vez | `sk_date` | Duplicidade de calendário | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| `not_null + unique` em data completa | Generic | Evitar duas linhas para o mesmo dia | `full_date` é o grão real da dimensão | `full_date` | Quebra de join temporal | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| `not_null` em atributos temporais básicos | Generic | Garantir completude dos atributos de calendário | Não aceitar decomposição parcial | `day_number`, `day_of_year`, `week_of_year`, `year_month`, `year_quarter`, `year_number` | Perda de consistência analítica | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| `accepted_values` em números de calendário | Generic | Restringir domínio temporal | Dia da semana, mês, trimestre e semestre dentro de valores válidos | `day_of_week_number`, `month_number`, `quarter_number`, `semester_number` | Valores inválidos de decomposição | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| `accepted_values` em nomes de calendário | Generic | Restringir rótulos de calendário | Nomes textuais fechados para dia, mês e trimestre | `day_of_week_name`, `month_name`, `quarter_name` | Inconsistência semântica | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| `accepted_values` em flags booleanas | Generic | Garantir flags binárias | Fim de semana e alta temporada devem ser booleanos | `is_weekend`, `is_high_season` | Cardinalidade indevida | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |

### Singular Tests

Não há testes singulares para este modelo.

### Unit Tests

Não há unit tests para este modelo.

## Matriz de Cobertura

| Categoria | Coberto |
|---|---|
| Primary Key | ✅ |
| Foreign Key | ❌ |
| Not Null | ✅ |
| Accepted Values | ✅ |
| Business Rules | ◐ |
| Temporal Rules | ◐ |
| Aggregations | ❌ |
| Referential Integrity | ❌ |
| Duplicate Detection | ✅ |
| Unit Tests | ❌ |

A cobertura é forte para integridade estrutural, mas ainda depende exclusivamente de generic tests para a coerência temporal interna. Não há testes que validem sequência contínua de datas, ausência de lacunas ou correlação explícita entre `full_date` e os atributos derivados.

## Fluxo de Validação

O modelo é protegido principalmente por testes de unicidade e domínios fechados. Isso impede duplicidade de dias e garante que os atributos gerados pelo spine do calendário permaneçam coerentes com o contrato analítico esperado. Como a dimensão é compartilhada por vários fatos, qualquer erro nessa camada propagaria falhas para múltiplos joins e análises temporais.

## Possíveis Riscos Ainda Não Cobertos

- Não há teste de continuidade temporal sem lacunas.
- Não há teste explícito de datas futuras ou passadas além do intervalo esperado pelo negócio.
- Não há validação cruzada entre `day_of_week_number` e `day_of_week_name` além do próprio domínio permitido.

# dim_customers

## Objetivo

Dimensão de clientes com uma linha por cliente cadastrado, acrescida de um membro técnico para cliente não informado. O modelo incorpora um endereço selecionado de forma determinística quando há múltiplos endereços.

## Regras de Negócio

- Cada cliente deve aparecer uma única vez.
- O endereço principal deve ser priorizado; na ausência dele, o endereço é escolhido de forma determinística.
- O membro técnico precisa existir para representar cliente não informado.
- Flags de endereço principal, ativo e membro técnico são booleanas.

## Colunas Críticas

| Coluna | Descrição | Criticidade |
|---|---|---|
| `sk_customer` | Chave substituta do cliente. | Alta |
| `nk_customer_id` | Identificador natural do cliente. | Alta |
| `legal_name` | Nome legal / razão social. | Alta |
| `nk_address_id` | Endereço selecionado para o cliente. | Média |
| `is_primary_address` | Flag do endereço principal. | Média |
| `is_active` | Flag de ativo. | Média |
| `is_technical_member` | Flag de membro técnico. | Alta |

## Testes Implementados

### Generic Tests

| Nome do teste | Tipo | Objetivo | Regra protegida | Colunas envolvidas | Risco mitigado | Arquivo |
|---|---|---|---|---|---|---|
| Chave substituta do cliente | Generic | Garantir unicidade do surrogate key | Um registro por cliente | `sk_customer` | Duplicidade dimensional | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Chave natural do cliente | Generic | Garantir unicidade do ID natural | Um cliente por ID | `nk_customer_id` | Duplicidade de cadastro | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Nome legal obrigatório | Generic | Garantir preenchimento cadastral | Cliente sem nome legal não é permitido | `legal_name` | Cadastro incompleto | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Flag de endereço principal | Generic | Garantir booleanidade | Campo não pode assumir valores fora de `true/false` | `is_primary_address` | Estados inválidos | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Flag de ativo | Generic | Garantir booleanidade | Cliente ativo/inativo apenas | `is_active` | Classificação inconsistente | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Flag de membro técnico | Generic | Garantir booleanidade | Registro técnico apenas em dois estados | `is_technical_member` | Quebra de contrato técnico | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |

### Singular Tests

Não há testes singulares para este modelo.

### Unit Tests

Não há unit tests para este modelo.

## Matriz de Cobertura

| Categoria | Coberto |
|---|---|
| Primary Key | ✅ |
| Foreign Key | ❌ |
| Not Null | ✅ |
| Accepted Values | ✅ |
| Business Rules | ◐ |
| Temporal Rules | ❌ |
| Aggregations | ❌ |
| Referential Integrity | ❌ |
| Duplicate Detection | ✅ |
| Unit Tests | ❌ |

A cobertura protege bem a integridade estrutural da dimensão, mas não há teste específico para validar a lógica determinística de seleção de endereço ou a consistência do relacionamento do endereço com a entidade de origem.

## Fluxo de Validação

A validação impede duplicidade de clientes e elimina estados inválidos nas flags de negócio. Isso é suficiente para garantir a base da dimensão, porém a regra de seleção do endereço continua dependente da SQL do modelo e não é exercitada por teste dedicado.

## Possíveis Riscos Ainda Não Cobertos

- Não há teste de integridade entre cliente e endereço selecionado.
- Não há teste para garantir que o endereço principal seja priorizado quando existir.
- Não há validação de consistência do conjunto de campos de contato ou documento fiscal.

# dim_employees

## Objetivo

Dimensão de funcionários com registros reais e membros técnicos de suporte operacional, incluindo entradas para migração legada, sistema de e-commerce e funcionário não informado.

## Regras de Negócio

- Cada funcionário ou membro técnico deve ter uma chave natural única.
- Os membros técnicos precisam existir para suporte analítico e rastreabilidade.
- `nk_primary_location_id` deve apontar para uma localização existente quando preenchido.
- `is_active` e `is_technical_member` são flags booleanas.

## Colunas Críticas

| Coluna | Descrição | Criticidade |
|---|---|---|
| `sk_employee` | Chave substituta do funcionário. | Alta |
| `nk_employee_id` | Identificador natural ou técnico. | Alta |
| `full_name` | Nome do funcionário / agente técnico. | Alta |
| `role` | Papel ou classificação técnica. | Alta |
| `nk_primary_location_id` | Localização principal. | Média |
| `is_active` | Flag de ativo. | Média |
| `is_technical_member` | Flag de membro técnico. | Alta |

## Testes Implementados

### Generic Tests

| Nome do teste | Tipo | Objetivo | Regra protegida | Colunas envolvidas | Risco mitigado | Arquivo |
|---|---|---|---|---|---|---|
| Chave substituta do funcionário | Generic | Garantir unicidade do surrogate key | Um registro por funcionário | `sk_employee` | Duplicidade dimensional | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Chave natural do funcionário | Generic | Garantir unicidade do ID natural | Um funcionário por ID | `nk_employee_id` | Colisão de identidades | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Nome completo obrigatório | Generic | Garantir identificação do registro | Nome não pode ser nulo | `full_name` | Registro sem identificação | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Cargo obrigatório | Generic | Garantir classificação mínima | Funcionário precisa ter `role` | `role` | Dimensão sem categorização | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Localização principal referenciada | Generic | Validar chave natural para localização | `nk_primary_location_id` deve existir em `dim_locations` | `nk_primary_location_id` | Quebra de rastreabilidade operacional | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Flag de ativo | Generic | Garantir booleanidade | Campo binário apenas | `is_active` | Estados inválidos | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Flag de membro técnico | Generic | Garantir booleanidade | Campo binário apenas | `is_technical_member` | Quebra do contrato técnico | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |

### Singular Tests

Não há testes singulares para este modelo.

### Unit Tests

Não há unit tests para este modelo.

## Matriz de Cobertura

| Categoria | Coberto |
|---|---|
| Primary Key | ✅ |
| Foreign Key | ✅ |
| Not Null | ✅ |
| Accepted Values | ✅ |
| Business Rules | ◐ |
| Temporal Rules | ❌ |
| Aggregations | ❌ |
| Referential Integrity | ✅ |
| Duplicate Detection | ✅ |
| Unit Tests | ❌ |

A cobertura é sólida para identidade e relacionamento com localização. A regra temporal entre `hire_date` e `termination_date` existe na SQL e é reforçada por teste singular, o que amplia a proteção do modelo.

## Fluxo de Validação

A dimensão fica protegida contra duplicidade, nulidade e domínios inválidos. O relacionamento com `dim_locations` evita que o funcionário aponte para uma localização inexistente, o que é importante para análises regionais e de alocação operacional.

## Possíveis Riscos Ainda Não Cobertos

- Não há teste específico para a coerência entre `hire_date`, `termination_date` e `is_active` além da validação singular existente.
- Não há validação de formato de CPF ou e-mail.

# dim_locations

## Objetivo

Dimensão conformada de lojas, armazéns e demais localizações físicas, com membro técnico para localização não informada.

## Regras de Negócio

- Cada localização deve ser única por chave substituta e natural.
- O tipo de localização é restrito a `store`, `warehouse` e `nao_informado`.
- Há um membro técnico para localizações ausentes.
- Flags de ativo e membro técnico são booleanas.

## Colunas Críticas

| Coluna | Descrição | Criticidade |
|---|---|---|
| `sk_location` | Chave substituta da localização. | Alta |
| `nk_location_id` | Identificador natural. | Alta |
| `location_name` | Nome da localização. | Alta |
| `location_type` | Tipo da localização. | Alta |
| `is_active` | Flag de ativo. | Média |
| `is_technical_member` | Flag de membro técnico. | Alta |

## Testes Implementados

### Generic Tests

| Nome do teste | Tipo | Objetivo | Regra protegida | Colunas envolvidas | Risco mitigado | Arquivo |
|---|---|---|---|---|---|---|
| Chave substituta da localização | Generic | Garantir unicidade | Uma linha por localização | `sk_location` | Duplicidade dimensional | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Chave natural da localização | Generic | Garantir unicidade | Uma localização por ID natural | `nk_location_id` | Colisão cadastral | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Nome da localização obrigatório | Generic | Garantir completude cadastral | Localização sem nome não é aceita | `location_name` | Cadastro incompleto | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Tipo da localização | Generic | Restringir domínio | Apenas tipos previstos pela SQL | `location_type` | Classificação inválida | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Flag de ativo | Generic | Garantir booleanidade | Apenas `true/false` | `is_active` | Estado indevido | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Flag de membro técnico | Generic | Garantir booleanidade | Apenas `true/false` | `is_technical_member` | Quebra do contrato técnico | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |

### Singular Tests

Não há testes singulares para este modelo.

### Unit Tests

Não há unit tests para este modelo.

## Matriz de Cobertura

| Categoria | Coberto |
|---|---|
| Primary Key | ✅ |
| Foreign Key | ❌ |
| Not Null | ✅ |
| Accepted Values | ✅ |
| Business Rules | ◐ |
| Temporal Rules | ❌ |
| Aggregations | ❌ |
| Referential Integrity | ❌ |
| Duplicate Detection | ✅ |
| Unit Tests | ❌ |

A dimensão está bem protegida estruturalmente, mas não há um teste específico para validar aderência semântica entre tipo e atributos operacionais, nem para cruzar localizações ativas com fatos consumidores.

## Fluxo de Validação

Os testes garantem que a dimensão mantenha unicidade e valores consistentes. Como é uma dimensão conformada, isso evita o surgimento de localizações espúrias nos fatos e preserva a qualidade dos joins analíticos.

## Possíveis Riscos Ainda Não Cobertos

- Não há validação de integridade entre tipo da localização e atributos logísticos.
- Não há teste de consistência temporal da ativação/inativação da localização.

# dim_products

## Objetivo

Dimensão de produtos no grão de variante comercial ou SKU, consolidando dados da variante, do produto pai, da marca e da categoria utilizada diretamente pelo produto.

## Regras de Negócio

- Cada variante de produto deve ser única.
- `product_name`, `brand_name` e `category_name` são campos obrigatórios.
- `is_brand_active`, `is_category_active`, `is_product_active`, `is_variant_active` e `is_technical_member` são flags booleanas.
- A dimensão tolera ausência de marca ou categoria e substitui por rótulos técnicos padronizados.
- O modelo não utiliza a hierarquia de categoria pai.

## Colunas Críticas

| Coluna | Descrição | Criticidade |
|---|---|---|
| `sk_product` | Chave substituta da variante. | Alta |
| `nk_product_variant_id` | Identificador natural da variante. | Alta |
| `nk_product_id` | Identificador natural do produto pai. | Alta |
| `product_name` | Nome do produto. | Alta |
| `brand_name` | Nome da marca. | Alta |
| `category_name` | Nome da categoria. | Alta |
| `is_product_active` | Flag do produto pai. | Média |
| `is_variant_active` | Flag da variante. | Média |
| `is_technical_member` | Flag de membro técnico. | Alta |

## Testes Implementados

### Generic Tests

| Nome do teste | Tipo | Objetivo | Regra protegida | Colunas envolvidas | Risco mitigado | Arquivo |
|---|---|---|---|---|---|---|
| Chave substituta da variante | Generic | Garantir unicidade | Uma linha por SKU analítico | `sk_product` | Duplicidade dimensional | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Chave natural da variante | Generic | Garantir unicidade | Cada variante aparece uma única vez | `nk_product_variant_id` | Colisão de SKU | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Produto pai obrigatório | Generic | Garantir referência ao produto base | Variante precisa apontar para um produto pai | `nk_product_id` | Produto órfão | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Nome do produto | Generic | Garantir preenchimento | Produto sem nome não é aceito | `product_name` | Cadastro incompleto | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Nome da marca | Generic | Garantir preenchimento após fallback | Marca precisa ser resolvida pela SQL | `brand_name` | Dimensão com atributo vazio | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Nome da categoria | Generic | Garantir preenchimento após fallback | Categoria precisa ser resolvida pela SQL | `category_name` | Classificação incompleta | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Flags de marca/categoria/produto/variante | Generic | Garantir booleanidade | Flags não podem assumir outros tipos | `is_brand_active`, `is_category_active`, `is_product_active`, `is_variant_active`, `is_technical_member` | Estado binário inválido | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |

### Singular Tests

Não há testes singulares para este modelo.

### Unit Tests

Não há unit tests para este modelo.

## Matriz de Cobertura

| Categoria | Coberto |
|---|---|
| Primary Key | ✅ |
| Foreign Key | ❌ |
| Not Null | ✅ |
| Accepted Values | ✅ |
| Business Rules | ◐ |
| Temporal Rules | ❌ |
| Aggregations | ❌ |
| Referential Integrity | ❌ |
| Duplicate Detection | ✅ |
| Unit Tests | ❌ |

A dimensão está bem protegida em termos de completude e classificação, mas não há teste específico para validar a coerência aritmética de métricas de margem ou impostos, que permanecem sob responsabilidade da camada `intermediate`.

## Fluxo de Validação

Os testes impedem que variantes duplicadas ou mal classificadas entrem na camada analítica. A presença de flags booleanas validadas reduz o risco de inconsistências em filtros de BI e dashboards.

## Possíveis Riscos Ainda Não Cobertos

- Não há teste na camada `marts` para validar margem, `total_tax_rate` ou `is_profitable`; essa consistência é tratada antes, em `intermediate`.
- Não há teste de relacionamento explícito com marca e categoria, apenas preenchimento dos atributos derivados.

# dim_suppliers

## Objetivo

Dimensão de fornecedores usada nas análises de compras, abastecimento e recebimentos de mercadorias, com membro técnico para fornecedor não informado.

## Regras de Negócio

- Cada fornecedor deve ser único por chave natural.
- `legal_name` é obrigatório.
- `is_active` e `is_technical_member` devem ser booleanos.
- O membro técnico deve permanecer disponível para casos sem fornecedor resolvido.

## Colunas Críticas

| Coluna | Descrição | Criticidade |
|---|---|---|
| `sk_supplier` | Chave substituta do fornecedor. | Alta |
| `nk_supplier_id` | Identificador natural do fornecedor. | Alta |
| `legal_name` | Razão social / nome legal. | Alta |
| `is_active` | Flag de ativo. | Média |
| `is_technical_member` | Flag de membro técnico. | Alta |

## Testes Implementados

### Generic Tests

| Nome do teste | Tipo | Objetivo | Regra protegida | Colunas envolvidas | Risco mitigado | Arquivo |
|---|---|---|---|---|---|---|
| Chave substituta do fornecedor | Generic | Garantir unicidade | Uma linha por fornecedor | `sk_supplier` | Duplicidade dimensional | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Chave natural do fornecedor | Generic | Garantir unicidade | Cada fornecedor aparece uma única vez | `nk_supplier_id` | Colisão de cadastro | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Nome legal obrigatório | Generic | Garantir completude | Fornecedor sem nome não é aceito | `legal_name` | Cadastro incompleto | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Flag de ativo | Generic | Garantir booleanidade | Apenas `true/false` | `is_active` | Estado inválido | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Flag de membro técnico | Generic | Garantir booleanidade | Apenas `true/false` | `is_technical_member` | Quebra do contrato técnico | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |

### Singular Tests

Não há testes singulares para este modelo.

### Unit Tests

Não há unit tests para este modelo.

## Matriz de Cobertura

| Categoria | Coberto |
|---|---|
| Primary Key | ✅ |
| Foreign Key | ❌ |
| Not Null | ✅ |
| Accepted Values | ✅ |
| Business Rules | ◐ |
| Temporal Rules | ❌ |
| Aggregations | ❌ |
| Referential Integrity | ❌ |
| Duplicate Detection | ✅ |
| Unit Tests | ❌ |

A dimensão é robusta estruturalmente, mas não há validação específica para documentos fiscais, país ou canais de contato, que são atributos descritivos sem testes dedicados nesta camada.

## Fluxo de Validação

A cobertura impede duplicidade e garante preenchimento dos campos estruturais mínimos. Isso é suficiente para manter o fornecedor como dimensão confiável para compras e recebimentos.

## Possíveis Riscos Ainda Não Cobertos

- Não há teste de formato para `tax_id`, `email` ou `phone`.
- Não há teste de relacionamento com pedidos ou recebimentos, o que é esperado para uma dimensão, mas ainda depende do uso correto pelos fatos.

# fact_order_items

## Objetivo

Fato de vendas no grão de um item por pedido. O modelo concentra valores comerciais, impostos, desconto alocado, custo padrão e margem estimada por SKU.

## Regras de Negócio

- O grão é um item de pedido.
- Desconto do pedido é alocado proporcionalmente entre os itens com base no valor bruto da linha.
- A dimensão resolve cliente, produto, localização, funcionário e data do pedido.
- O status do pedido controla as flags `is_cancelled`, `is_paid`, `is_confirmed` e `is_draft`.
- `order_item_count` é um contador aditivo fixo em 1.
- `estimated_cost_of_goods_sold` e `estimated_gross_profit` derivam de `quantity_ordered`, `standard_unit_cost` e `net_line_total`.

## Colunas Críticas

| Coluna | Descrição | Criticidade |
|---|---|---|
| `sk_order_item` | Chave substituta do item. | Alta |
| `nk_order_item_id` | Identificador natural do item. | Alta |
| `nk_order_id` | Identificador natural do pedido. | Alta |
| `sk_product` | FK para produto. | Alta |
| `sk_customer` | FK para cliente. | Alta |
| `sk_location` | FK para localização. | Alta |
| `sk_employee` | FK para funcionário. | Alta |
| `sk_date` | FK para data. | Alta |
| `order_status` | Status do pedido. | Alta |
| `gross_line_total` | Valor bruto da linha. | Alta |
| `allocated_discount_amount` | Desconto alocado. | Alta |
| `net_line_total` | Valor líquido da linha. | Alta |
| `estimated_cost_of_goods_sold` | Custo estimado vendido. | Média |
| `estimated_gross_profit` | Lucro estimado. | Média |
| `order_item_count` | Contador aditivo. | Média |

## Testes Implementados

### Generic Tests

| Nome do teste | Tipo | Objetivo | Regra protegida | Colunas envolvidas | Risco mitigado | Arquivo |
|---|---|---|---|---|---|---|
| Chaves do item de pedido | Generic | Garantir unicidade do fato | Cada item aparece uma única vez | `sk_order_item`, `nk_order_item_id` | Duplicidade no grão | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Pedido e número comercial obrigatórios | Generic | Garantir completude do cabeçalho | Item precisa estar ligado a pedido válido | `nk_order_id`, `order_number` | Item órfão | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Dimensões relacionadas | Generic | Garantir integridade referencial | Produto, cliente, localização, funcionário e data devem existir nas dimensões conformadas | `sk_product`, `sk_customer`, `sk_location`, `sk_employee`, `sk_date` | Fato órfã | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Canal do pedido | Generic | Garantir preenchimento | Canal não pode ser nulo | `channel` | Segmentação incorreta | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Status do pedido | Generic | Restringir domínio | Apenas `paid`, `confirmed`, `cancelled`, `draft` | `order_status` | Classificação inconsistente | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Quantidade, preço e valores da linha | Generic | Garantir completude financeira | Valores-base não podem ser nulos | `quantity_ordered`, `unit_price`, `gross_line_total`, `allocated_discount_amount`, `net_line_total`, `icms_rate`, `ipi_rate`, `icms_amount`, `ipi_amount`, `total_tax_amount`, `total_with_taxes` | Fato analiticamente incompleta | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Flags derivadas do pedido | Generic | Garantir booleanidade | `is_cancelled`, `is_paid`, `is_confirmed`, `is_draft` devem ser booleanas | Flags de status | Filtro BI quebrado | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Contador aditivo | Generic | Garantir semântica do contador | `order_item_count` deve permanecer em 1 | `order_item_count` | Duplicidade de agregação | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |

### Singular Tests

| Nome do teste | Tipo | Objetivo | Regra protegida | Colunas envolvidas | Motivações | Risco mitigado | Arquivo |
|---|---|---|---|---|---|---|---|
| `fact_order_items_amount_consistency` | Singular | Validar a matemática da linha | `net_line_total = gross_line_total - allocated_discount_amount` e as métricas derivadas devem fechar | `gross_line_total`, `allocated_discount_amount`, `net_line_total`, `quantity_ordered`, `standard_unit_cost`, `estimated_cost_of_goods_sold`, `estimated_gross_profit` | Protege a consistência financeira do fato | Erro de cálculo de desconto, custo e lucro | [src/dbt/tests/fact_order_items_amount_consistency.sql](../../src/dbt/tests/fact_order_items_amount_consistency.sql) |
| `fact_order_items_status_flags` | Singular | Validar coerência entre status e flags | O status deve acionar apenas a flag correspondente | `order_status`, `is_cancelled`, `is_paid`, `is_confirmed`, `is_draft` | Garante que o contrato analítico de status permaneça estável | Segmentação incorreta em dashboards | [src/dbt/tests/fact_order_items_status_flags.sql](../../src/dbt/tests/fact_order_items_status_flags.sql) |

### Unit Tests

Não há unit tests para este modelo.

## Matriz de Cobertura

| Categoria | Coberto |
|---|---|
| Primary Key | ✅ |
| Foreign Key | ✅ |
| Not Null | ✅ |
| Accepted Values | ✅ |
| Business Rules | ✅ |
| Temporal Rules | ◐ |
| Aggregations | ✅ |
| Referential Integrity | ✅ |
| Duplicate Detection | ✅ |
| Unit Tests | ❌ |

A cobertura é muito forte: o modelo protege identidade, integridade dimensional, domínio de status e consistência aritmética. O único ponto ainda parcialmente coberto é a lógica temporal associada à data do pedido, que não possui teste específico de ordem cronológica ou janela futura.

## Fluxo de Validação

A combinação de generic e singular tests garante que o fato não tenha duplicidade no grão, que os relacionamentos com dimensões estejam íntegros e que os valores financeiros fechem matematicamente. Isso reduz o risco de dupla contagem, de linhas órfãs e de métricas inconsistentes em análises de receita e rentabilidade.

## Possíveis Riscos Ainda Não Cobertos

- Não há teste de reconciliação com `orders.total` ou de soma do total por pedido.
- Não há teste explícito para a coerência temporal de `placed_at` em relação a outras datas operacionais.

# fact_payments

## Objetivo

Fato financeira no grão de uma transação de pagamento, mantendo separadamente a data de criação do pedido e a data efetiva do pagamento.

## Regras de Negócio

- O pagamento pertence a um pedido e a um cliente.
- O modelo não cria relação direta com produto.
- O status do pagamento determina os indicadores `is_paid`, `is_refunded`, `is_pending` e `is_cancelled`.
- `paid_amount` e `refunded_amount` só assumem valor quando o status correspondente está presente.
- `payment_count` é um contador aditivo fixo em 1.

## Colunas Críticas

| Coluna | Descrição | Criticidade |
|---|---|---|
| `sk_payment` | Chave substituta do pagamento. | Alta |
| `nk_payment_id` | Identificador natural do pagamento. | Alta |
| `nk_order_id` | Identificador natural do pedido. | Alta |
| `sk_customer` | FK para cliente. | Alta |
| `sk_location` | FK para localização. | Alta |
| `sk_order_date` | FK para data do pedido. | Alta |
| `sk_payment_date` | FK para data efetiva do pagamento. | Média |
| `payment_status` | Status do pagamento. | Alta |
| `payment_amount` | Valor da transação. | Alta |
| `paid_amount` | Valor pago. | Média |
| `refunded_amount` | Valor estornado. | Média |
| `payment_count` | Contador aditivo. | Média |

## Testes Implementados

### Generic Tests

| Nome do teste | Tipo | Objetivo | Regra protegida | Colunas envolvidas | Risco mitigado | Arquivo |
|---|---|---|---|---|---|---|
| Chaves do pagamento | Generic | Garantir unicidade | Cada transação aparece uma única vez | `sk_payment`, `nk_payment_id` | Duplicidade do fato | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Pedido e número do pedido obrigatórios | Generic | Garantir rastreabilidade | Pagamento sempre aponta para um pedido | `nk_order_id`, `order_number` | Pagamento órfão | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Clientes, localidades e datas relacionadas | Generic | Validar integridade referencial | Cliente, local e datas devem existir nas dimensões | `sk_customer`, `sk_location`, `sk_order_date`, `sk_payment_date` | Quebra de join analítico | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Canal, status e método | Generic | Garantir preenchimento e domínio | `channel`, `order_status`, `method`, `payment_status` devem ser válidos | Cabeçalho da transação | Classificação errada | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Parcelas e valor da transação | Generic | Garantir completude | `installments` e `payment_amount` não podem ser nulos | Valores financeiros | Pagamento incompleto | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Flags de status do pagamento | Generic | Garantir booleanidade | `is_paid`, `is_refunded`, `is_pending`, `is_cancelled` devem ser booleanas | Flags derivadas | Leitura incorreta em BI | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Medidas derivadas | Generic | Garantir completude | `paid_amount`, `refunded_amount` e `payment_count` são obrigatórios | Medidas analíticas | Fato incompleta | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Contador aditivo | Generic | Garantir semântica do fato | `payment_count` deve ser 1 | `payment_count` | Dupla contagem | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |

### Singular Tests

| Nome do teste | Tipo | Objetivo | Regra protegida | Colunas envolvidas | Motivações | Risco mitigado | Arquivo |
|---|---|---|---|---|---|---|---|
| `fact_payments_amount_and_status_consistency` | Singular | Validar a relação entre status e valores monetários | Pagamentos aprovados, reembolsados, pendentes e cancelados devem refletir os valores corretos nas medidas derivadas | `payment_status`, `payment_amount`, `paid_amount`, `refunded_amount`, `is_paid`, `is_refunded`, `is_pending`, `is_cancelled` | Protege o contrato financeiro do modelo | Divergência entre status e valor reconhecido | [src/dbt/tests/fact_payments_amount_and_status_consistency.sql](../../src/dbt/tests/fact_payments_amount_and_status_consistency.sql) |

### Unit Tests

Não há unit tests para este modelo.

## Matriz de Cobertura

| Categoria | Coberto |
|---|---|
| Primary Key | ✅ |
| Foreign Key | ✅ |
| Not Null | ✅ |
| Accepted Values | ✅ |
| Business Rules | ✅ |
| Temporal Rules | ◐ |
| Aggregations | ✅ |
| Referential Integrity | ✅ |
| Duplicate Detection | ✅ |
| Unit Tests | ❌ |

A cobertura é forte em integridade financeira e dimensional. O modelo protege a leitura do status do pagamento e impede que valores derivados fiquem desalinhados do contrato de negócio.

## Fluxo de Validação

Os generic tests evitam lacunas estruturais e órfãos dimensionais; o singular test fecha a lógica entre status e valores monetários. Isso reduz o risco de métricas de caixa e conciliação de pagamentos divergirem do estado operacional.

## Possíveis Riscos Ainda Não Cobertos

- Não há teste específico para ordem cronológica entre `placed_at` e `paid_at`.
- Não há reconciliação com total do pedido por pedido ou por cliente.

# fact_purchase_order_items

## Objetivo

Fato de compras no grão de um item por pedido de compra. Preserva valores na moeda original e em BRL, com a data prevista de entrega mantida como papel temporal distinto.

## Regras de Negócio

- O grão é um item de pedido de compra.
- Produto, fornecedor, localização, funcionário e datas devem ser resolvidos por dimensão conformada.
- `purchase_order_status` segue o domínio definido na camada intermediária.
- A conversão para BRL depende de moeda e taxa de câmbio.
- `is_expected_delivery_overdue` deriva da comparação entre `expected_delivery_at` e a data corrente.
- `purchase_order_item_count` é fixo em 1.

## Colunas Críticas

| Coluna | Descrição | Criticidade |
|---|---|---|
| `sk_purchase_order_item` | Chave substituta do item. | Alta |
| `nk_purchase_order_item_id` | Identificador natural do item. | Alta |
| `nk_purchase_order_id` | Identificador natural do pedido. | Alta |
| `sk_product` | FK para produto. | Alta |
| `sk_supplier` | FK para fornecedor. | Alta |
| `sk_location` | FK para localização. | Alta |
| `sk_employee` | FK para funcionário comprador. | Alta |
| `sk_order_date` | FK para data do pedido. | Alta |
| `sk_expected_delivery_date` | FK para data prevista. | Alta |
| `purchase_order_status` | Status do pedido de compra. | Alta |
| `currency` | Moeda original. | Alta |
| `unit_cost_brl` | Custo convertido. | Média |
| `line_total_brl` | Total convertido. | Média |
| `is_expected_delivery_overdue` | Flag de atraso esperado. | Alta |
| `purchase_order_item_count` | Contador aditivo. | Média |

## Testes Implementados

### Generic Tests

| Nome do teste | Tipo | Objetivo | Regra protegida | Colunas envolvidas | Risco mitigado | Arquivo |
|---|---|---|---|---|---|---|
| Chaves do item de compra | Generic | Garantir unicidade | Cada item aparece uma única vez | `sk_purchase_order_item`, `nk_purchase_order_item_id` | Duplicidade do fato | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Pedido de compra e número comercial | Generic | Garantir rastreabilidade | Item precisa apontar para um pedido válido | `nk_purchase_order_id`, `po_number` | Item órfão | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Dimensões relacionadas | Generic | Validar integridade referencial | Produto, fornecedor, local, funcionário e datas devem existir | `sk_product`, `sk_supplier`, `sk_location`, `sk_employee`, `sk_order_date`, `sk_expected_delivery_date` | Quebra de join analítico | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Status, moeda e custos | Generic | Garantir completude | Status, moeda, quantidade, custos e datas obrigatórios | `purchase_order_status`, `currency`, `quantity_ordered`, `unit_cost_original_currency`, `line_total_original_currency`, `placed_at`, `expected_delivery_at` | Fato incompleta | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Flag de atraso esperado | Generic | Garantir booleanidade | `is_expected_delivery_overdue` deve ser booleano | `is_expected_delivery_overdue` | Estado inválido | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Contador aditivo | Generic | Garantir semântica do fato | `purchase_order_item_count` deve ser 1 | `purchase_order_item_count` | Dupla contagem | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |

### Singular Tests

| Nome do teste | Tipo | Objetivo | Regra protegida | Colunas envolvidas | Motivações | Risco mitigado | Arquivo |
|---|---|---|---|---|---|---|---|
| `fact_purchase_order_items_currency_and_overdue_consistency` | Singular | Validar conversão monetária e atraso previsto | Valores em BRL devem respeitar a moeda original e a data prevista deve controlar a flag de atraso | `currency`, `exchange_rate_sell`, `unit_cost_original_currency`, `line_total_original_currency`, `unit_cost_brl`, `line_total_brl`, `expected_delivery_at`, `is_expected_delivery_overdue` | Garante consistência financeira e temporal do fato | Conversão incorreta e flag de atraso invertida | [src/dbt/tests/fact_purchase_order_items_currency_and_overdue_consistency.sql](../../src/dbt/tests/fact_purchase_order_items_currency_and_overdue_consistency.sql) |

### Unit Tests

Não há unit tests para este modelo.

## Matriz de Cobertura

| Categoria | Coberto |
|---|---|
| Primary Key | ✅ |
| Foreign Key | ✅ |
| Not Null | ✅ |
| Accepted Values | ✅ |
| Business Rules | ✅ |
| Temporal Rules | ✅ |
| Aggregations | ✅ |
| Referential Integrity | ✅ |
| Duplicate Detection | ✅ |
| Unit Tests | ❌ |

A cobertura é excelente para compras porque protege relacionamento, moeda, atraso esperado e semântica do contador. A única lacuna relevante é a ausência de teste de reconciliação com totais do pedido de compra.

## Fluxo de Validação

Os generic tests evitam fatos órfãos e domínios inválidos; o singular test garante que a conversão monetária e a flag de atraso não se desviem da lógica implementada na SQL.

## Possíveis Riscos Ainda Não Cobertos

- Não há reconciliação com subtotal/total do pedido de compra.
- Não há teste explícito para o caso de moeda estrangeira sem taxa de câmbio, embora a SQL trate isso como `NULL`.

# fact_goods_receipt_items

## Objetivo

Fato de recebimentos físicos no grão de um item por evento de recebimento de mercadoria. O modelo relaciona recebimento, pedido de compra, funcionário, produto, fornecedor, localização e datas de operação.

## Regras de Negócio

- O grão é um item de recebimento por evento.
- O saldo pendente após cada recebimento é acumulado por item de pedido de compra.
- O valor recebido pode ser preservado na moeda original e convertido para BRL quando possível.
- `is_fully_received` e `is_partial_receipt` são derivados da quantidade acumulada.
- `delivery_variance_days` e `is_late_receipt` dependem da diferença entre recebimento e data prevista.
- `goods_receipt_item_count` é fixo em 1.

## Colunas Críticas

| Coluna | Descrição | Criticidade |
|---|---|---|
| `sk_goods_receipt_item` | Chave substituta do item recebido. | Alta |
| `nk_goods_receipt_item_id` | Identificador natural do item recebido. | Alta |
| `nk_purchase_order_item_id` | Item comprado associado. | Alta |
| `nk_purchase_order_id` | Pedido de compra associado. | Alta |
| `sk_product` | FK para produto. | Alta |
| `sk_supplier` | FK para fornecedor. | Alta |
| `sk_location` | FK para localização. | Alta |
| `sk_employee` | FK para funcionário receptor. | Alta |
| `sk_receipt_date` | Data do recebimento. | Alta |
| `sk_order_date` | Data de emissão do pedido. | Alta |
| `sk_expected_delivery_date` | Data prevista. | Alta |
| `quantity_received` | Quantidade recebida. | Alta |
| `cumulative_quantity_received` | Quantidade acumulada. | Alta |
| `remaining_quantity_after_receipt` | Saldo pendente. | Alta |
| `is_fully_received` | Flag de recebimento total. | Média |
| `is_partial_receipt` | Flag de recebimento parcial. | Média |
| `delivery_variance_days` | Diferença em dias. | Média |
| `is_late_receipt` | Flag de atraso. | Alta |

## Testes Implementados

### Generic Tests

| Nome do teste | Tipo | Objetivo | Regra protegida | Colunas envolvidas | Risco mitigado | Arquivo |
|---|---|---|---|---|---|---|
| Chaves do item recebido | Generic | Garantir unicidade | Cada item recebido aparece uma única vez | `sk_goods_receipt_item`, `nk_goods_receipt_item_id` | Duplicidade do fato | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Recebimento e pedido vinculados | Generic | Garantir rastreabilidade | Recebimento sempre ligado a um pedido e a um item comprado | `nk_goods_receipt_id`, `nk_purchase_order_item_id`, `nk_purchase_order_id`, `po_number` | Fato órfã | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Dimensões relacionadas | Generic | Validar integridade referencial | Produto, fornecedor, localização, funcionário e datas devem existir | `sk_product`, `sk_supplier`, `sk_location`, `sk_employee`, `sk_receipt_date`, `sk_order_date`, `sk_expected_delivery_date` | Quebra de join analítico | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Status, moeda e quantidades | Generic | Garantir completude | Campos operacionais e financeiros obrigatórios | `purchase_order_status`, `currency`, `quantity_ordered`, `quantity_received`, `cumulative_quantity_received`, `remaining_quantity_after_receipt`, `unit_cost_original_currency`, `received_value_original_currency`, `placed_at`, `expected_delivery_at`, `received_at`, `delivery_variance_days` | Fato incompleta | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Flags de recebimento | Generic | Garantir booleanidade | `is_fully_received`, `is_partial_receipt`, `is_late_receipt` devem ser booleanas | Flags de negócio | Leitura incorreta em BI | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Contador aditivo | Generic | Garantir semântica do fato | `goods_receipt_item_count` deve ser 1 | `goods_receipt_item_count` | Dupla contagem | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |

### Singular Tests

| Nome do teste | Tipo | Objetivo | Regra protegida | Colunas envolvidas | Motivações | Risco mitigado | Arquivo |
|---|---|---|---|---|---|---|---|
| `fact_goods_receipt_items_receipt_logic` | Singular | Validar saldo, valores recebidos e atraso | Quantidade acumulada, saldo pendente, valores e atraso devem bater com a fórmula da SQL | `quantity_ordered`, `quantity_received`, `cumulative_quantity_received`, `remaining_quantity_after_receipt`, `is_fully_received`, `is_partial_receipt`, `unit_cost_original_currency`, `received_value_original_currency`, `received_value_brl`, `delivery_variance_days`, `is_late_receipt` | Protege o comportamento acumulado do recebimento | Erro de cálculo de saldo ou atraso | [src/dbt/tests/fact_goods_receipt_items_receipt_logic.sql](../../src/dbt/tests/fact_goods_receipt_items_receipt_logic.sql) |

### Unit Tests

Não há unit tests para este modelo.

## Matriz de Cobertura

| Categoria | Coberto |
|---|---|
| Primary Key | ✅ |
| Foreign Key | ✅ |
| Not Null | ✅ |
| Accepted Values | ✅ |
| Business Rules | ✅ |
| Temporal Rules | ✅ |
| Aggregations | ✅ |
| Referential Integrity | ✅ |
| Duplicate Detection | ✅ |
| Unit Tests | ❌ |

A cobertura é muito forte porque o modelo combina integridade referencial com lógica acumulada e validação de atraso. A dimensão temporal e o cálculo de saldo pendente estão protegidos por teste singular específico.

## Fluxo de Validação

Os generic tests garantem que o recebimento esteja amarrado ao ecossistema analítico correto. O singular test cobre o comportamento mais sensível do modelo: saldo acumulado por item, conversão monetária e indicador de atraso.

## Possíveis Riscos Ainda Não Cobertos

- Não há teste de reconciliação com o total recebido por pedido de compra.
- Não há teste explícito para ausência de taxa de câmbio em moeda estrangeira.

# fact_stock_movements

## Objetivo

Fato de estoque no grão de uma movimentação individual. O modelo registra entradas e saídas por produto, localização, funcionário e data da movimentação.

## Regras de Negócio

- A movimentação é classificada como `entrada`, `saida` ou `nao_classificado`.
- O funcionário é resolvido pela presença do identificador, migração legada ou regra automática de e-commerce/sem identificação.
- `movement_count` é fixo em 1.
- `is_inbound` e `is_outbound` refletem a direção padronizada.

## Colunas Críticas

| Coluna | Descrição | Criticidade |
|---|---|---|
| `sk_stock_movement` | Chave substituta da movimentação. | Alta |
| `nk_stock_movement_id` | Identificador natural da movimentação. | Alta |
| `sk_product` | FK para produto. | Alta |
| `sk_location` | FK para localização. | Alta |
| `sk_employee` | FK para funcionário. | Alta |
| `sk_date` | FK para data. | Alta |
| `movement_type` | Tipo da movimentação. | Alta |
| `movement_direction` | Direção padronizada. | Alta |
| `quantity` | Quantidade com sinal. | Alta |
| `absolute_quantity` | Quantidade absoluta. | Média |
| `is_legacy_migration` | Flag de migração. | Média |
| `is_inbound` | Flag de entrada. | Média |
| `is_outbound` | Flag de saída. | Média |
| `movement_count` | Contador aditivo. | Média |

## Testes Implementados

### Generic Tests

| Nome do teste | Tipo | Objetivo | Regra protegida | Colunas envolvidas | Risco mitigado | Arquivo |
|---|---|---|---|---|---|---|
| Chaves da movimentação | Generic | Garantir unicidade | Cada movimentação aparece uma única vez | `sk_stock_movement`, `nk_stock_movement_id` | Duplicidade no fato | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Dimensões relacionadas | Generic | Garantir integridade referencial | Produto, localização, funcionário e data devem existir | `sk_product`, `sk_location`, `sk_employee`, `sk_date` | Fato órfã | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Classificação da movimentação | Generic | Restringir domínio | `movement_type` e `movement_direction` precisam ficar nos domínios definidos | `movement_type`, `movement_direction` | Classificação inválida | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Quantidade e contadores | Generic | Garantir completude | `quantity`, `absolute_quantity`, `movement_count`, `occurred_at` obrigatórios | Campos de fato | Fato incompleta | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Flags de direção e migração | Generic | Garantir booleanidade | `is_legacy_migration`, `is_inbound`, `is_outbound` devem ser booleanas | Flags de negócio | Leitura errada em BI | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Contador aditivo | Generic | Garantir semântica do fato | `movement_count` deve ser 1 | `movement_count` | Dupla contagem | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |

### Singular Tests

| Nome do teste | Tipo | Objetivo | Regra protegida | Colunas envolvidas | Motivações | Risco mitigado | Arquivo |
|---|---|---|---|---|---|---|---|
| `fact_stock_movements_direction_consistency` | Singular | Validar direção, sinal e classificação de migração | A direção normalizada deve bater com tipo, sinal da quantidade e flag de migração | `movement_type`, `movement_direction`, `quantity`, `absolute_quantity`, `is_legacy_migration`, `notes` | Protege a padronização operacional do estoque | Movimentação invertida ou mal classificada | [src/dbt/tests/fact_stock_movements_direction_consistency.sql](../../src/dbt/tests/fact_stock_movements_direction_consistency.sql) |

### Unit Tests

Não há unit tests para este modelo.

## Matriz de Cobertura

| Categoria | Coberto |
|---|---|
| Primary Key | ✅ |
| Foreign Key | ✅ |
| Not Null | ✅ |
| Accepted Values | ✅ |
| Business Rules | ✅ |
| Temporal Rules | ◐ |
| Aggregations | ✅ |
| Referential Integrity | ✅ |
| Duplicate Detection | ✅ |
| Unit Tests | ❌ |

A cobertura é boa porque protege a classificação da movimentação e a coerência do sinal. Ainda assim, a lógica de quantidade futura e janelas cronológicas poderia ser aprofundada se o negócio exigisse auditoria temporal mais rigorosa.

## Fluxo de Validação

Os generic tests garantem que a movimentação seja bem definida e amarrada às dimensões corretas. O singular test fecha o contrato entre tipo, direção, sinal da quantidade e flag de migração, que é o ponto mais sensível para análises de estoque.

## Possíveis Riscos Ainda Não Cobertos

- Não há teste explícito para `reference_table` e `nk_reference_id`.
- Não há teste de consistência entre `quantity` e `absolute_quantity` na camada `marts`.

# fact_return_items

## Objetivo

Fato de pós-venda no grão de um item pertencente a uma devolução. O modelo relaciona produto devolvido, possível produto de troca, cliente, localização, data, motivo e valores de reembolso.

## Regras de Negócio

- O grão é um item de devolução.
- O produto devolvido sempre deve existir; o produto de troca pode ser nulo em reembolsos.
- `action` define se o item é `refund` ou `exchange`.
- O item original do pedido e o pedido original precisam permanecer rastreáveis.
- `return_reason_group` é um domínio fechado.
- `returned_item_count` é fixo em 1.

## Colunas Críticas

| Coluna | Descrição | Criticidade |
|---|---|---|
| `sk_return_item` | Chave substituta do item devolvido. | Alta |
| `nk_return_item_id` | Identificador natural do item devolvido. | Alta |
| `nk_return_id` | Identificador natural da devolução. | Alta |
| `nk_order_item_id` | Item original vendido. | Alta |
| `nk_order_id` | Pedido original. | Alta |
| `sk_returned_product` | Produto devolvido. | Alta |
| `sk_exchange_product` | Produto de troca. | Média |
| `sk_customer` | FK para cliente. | Alta |
| `sk_location` | FK para localização. | Alta |
| `sk_date` | FK para data. | Alta |
| `return_status` | Status da devolução. | Alta |
| `return_reason_group` | Grupo de motivo. | Alta |
| `action` | Ação do item. | Alta |
| `quantity_returned` | Quantidade devolvida. | Média |
| `unit_refund_amount` | Reembolso unitário. | Média |
| `total_line_refund_amount` | Reembolso total da linha. | Média |
| `is_exchange` | Flag de troca. | Média |
| `is_refund` | Flag de reembolso. | Média |
| `has_refund_amount` | Flag de existência de valor. | Média |
| `returned_item_count` | Contador aditivo. | Média |

## Testes Implementados

### Generic Tests

| Nome do teste | Tipo | Objetivo | Regra protegida | Colunas envolvidas | Risco mitigado | Arquivo |
|---|---|---|---|---|---|---|
| Chaves da devolução | Generic | Garantir unicidade | Cada item devolvido aparece uma única vez | `sk_return_item`, `nk_return_item_id` | Duplicidade no fato | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Devolução e pedido original rastreáveis | Generic | Garantir integridade de origem | Item precisa apontar para devolução, item vendido e pedido original | `nk_return_id`, `nk_order_item_id`, `nk_order_id` | Quebra de rastreabilidade | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Dimensões relacionadas | Generic | Garantir integridade referencial | Produto, cliente, localização e data devem existir | `sk_returned_product`, `sk_exchange_product`, `sk_customer`, `sk_location`, `sk_date` | Fato órfã | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Status, motivo e ação | Generic | Restringir domínio | `return_status`, `return_reason_group`, `action` devem seguir lista fechada | Domínios analíticos | Classificação inconsistente | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Quantidades e valores | Generic | Garantir completude | Quantidade, valor unitário, valor total e flags operacionais devem ser preenchidos | Campos de valor | Fato incompleta | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Flags de troca/reembolso | Generic | Garantir booleanidade | `is_exchange`, `is_refund`, `has_refund_amount` devem ser booleanos | Flags de negócio | Leitura analítica errada | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |
| Contador aditivo | Generic | Garantir semântica do fato | `returned_item_count` deve ser 1 | `returned_item_count` | Dupla contagem | [src/dbt/models/marts/marts.yml](../../src/dbt/models/marts/marts.yml) |

### Singular Tests

| Nome do teste | Tipo | Objetivo | Regra protegida | Colunas envolvidas | Motivações | Risco mitigado | Arquivo |
|---|---|---|---|---|---|---|---|
| `fact_return_items_exchange_logic` | Singular | Validar a lógica de troca vs reembolso | Produto de troca só existe em `exchange`; flags precisam refletir a ação; contador deve permanecer em 1 | `action`, `sk_exchange_product`, `is_exchange`, `is_refund`, `returned_item_count` | Protege a semântica pós-venda | Mistura indevida entre troca e reembolso | [src/dbt/tests/fact_return_items_exchange_logic.sql](../../src/dbt/tests/fact_return_items_exchange_logic.sql) |

### Unit Tests

Não há unit tests para este modelo.

## Matriz de Cobertura

| Categoria | Coberto |
|---|---|
| Primary Key | ✅ |
| Foreign Key | ✅ |
| Not Null | ✅ |
| Accepted Values | ✅ |
| Business Rules | ✅ |
| Temporal Rules | ◐ |
| Aggregations | ✅ |
| Referential Integrity | ✅ |
| Duplicate Detection | ✅ |
| Unit Tests | ❌ |

A cobertura é alta porque o modelo protege a semântica de troca/reembolso e a rastreabilidade do item original. A principal lacuna é a ausência de validações adicionais para consistência temporal da devolução.

## Fluxo de Validação

A combinação de chaves únicas, relações com dimensões e testes singulares de troca/reembolso evita ambiguidade de pós-venda. Isso é especialmente importante para relatórios de devolução, churn e recuperação de receita.

## Possíveis Riscos Ainda Não Cobertos

- Não há teste explícito para `has_refund_amount` versus `total_line_refund_amount` nesta camada.
- Não há validação de cronologia entre `returned_at` e as datas do pedido original.

---

## Matriz Consolidada

| Modelo | Generic | Singular | Unit | Total | Cobertura |
|---|---:|---:|---:|---:|---|
| `dim_date` | 28 | 0 | 0 | 28 | Parcial |
| `dim_customers` | 11 | 0 | 0 | 11 | Parcial |
| `dim_employees` | 11 | 1 | 0 | 12 | Excelente |
| `dim_locations` | 11 | 0 | 0 | 11 | Parcial |
| `dim_products` | 20 | 0 | 0 | 20 | Parcial |
| `dim_suppliers` | 9 | 0 | 0 | 9 | Parcial |
| `fact_order_items` | 37 | 2 | 0 | 39 | Excelente |
| `fact_payments` | 33 | 1 | 0 | 34 | Excelente |
| `fact_purchase_order_items` | 31 | 1 | 0 | 32 | Excelente |
| `fact_goods_receipt_items` | 41 | 1 | 0 | 42 | Excelente |
| `fact_stock_movements` | 26 | 1 | 0 | 27 | Excelente |
| `fact_return_items` | 36 | 1 | 0 | 37 | Excelente |

### Leitura da matriz

- `Cobertura Excelente`: modelos com generic tests e pelo menos um singular test cobrindo regra de negócio ou consistência derivada.
- `Cobertura Parcial`: modelos com proteção estrutural robusta, mas sem singular tests dedicados.

---

## Estatísticas

| Métrica | Valor |
|---|---:|
| Modelos analisados | 12 |
| Generic Tests | 294 |
| Singular Tests | 8 |
| Unit Tests | 0 |
| Total de testes | 302 |
| Modelos sem testes | 0 |
| Modelos com cobertura parcial | 5 |
| Modelos com cobertura excelente | 7 |

---

## Análise Técnica

### Pontos Fortes

- A camada `marts` está fortemente protegida por testes de integridade estrutural: chaves únicas, `not_null`, domínios fechados e `relationships` são usados de forma consistente.
- As facts mais relevantes têm validação adicional por singular tests, cobrindo matemática financeira, status, atrasos, saldo acumulado e semântica de pós-venda.
- O padrão `data_tests` com `arguments` evita a depreciação de generic tests no dbt 1.11+.
- A modelagem usa membros técnicos de forma explícita, e isso está refletido nos testes de flags e relacionamentos.
- A estratégia trata com cuidado o que deve ser validado estruturalmente e o que deve ser validado por regra de negócio.

### Riscos Identificados

- Não existem unit tests; isso reduz a capacidade de isolar e provar transformações complexas com fixtures controladas.
- `dim_date` ainda não valida continuidade temporal, nem a relação entre o spine gerado e eventuais lacunas ou datas futuras.
- Algumas reconciliações de agregação importantes não estão cobertas na `marts`, como fechamento contra totais de cabeçalho ou totalizações por pedido.
- A maior parte da proteção temporal fica em singular tests, o que é eficaz, mas menos isolado do que unit tests para fórmulas complexas.
- A cobertura em dimensões é estruturalmente boa, porém algumas regras implícitas da SQL seguem sem teste dedicado, como a seleção determinística de endereço em `dim_customers`.

### Cobertura Funcional

| Dimensão | Avaliação | Justificativa |
|---|---|---|
| Integridade Referencial | 🟢 Excelente | Fatos possuem `relationships` explícitos para dimensões conformadas e, quando necessário, para fatos de origem. |
| Consistência Temporal | 🟡 Boa | Há validações relevantes em fatos com datas e flags derivadas, mas `dim_date` e alguns modelos ainda carecem de testes cronológicos mais finos. |
| Integridade das Métricas | 🟢 Excelente | Os fatos mais sensíveis contam com singular tests para fórmulas de valor, saldo, conversão e derivação de flags. |
| Regras de Negócio | 🟢 Excelente | O contrato de status, devolução, atraso, recebimento e movimentação de estoque está coberto. |
| Qualidade Dimensional | 🟢 Excelente | As dimensões principais têm unicidade, nulidade mínima e domínios fechados para flags e classificações. |
| Consistência dos Fatos | 🟢 Excelente | A maior parte dos fatos possui chave única, integridade dimensional e testes adicionais para regras de cálculo. |
| Qualidade das Chaves | 🟢 Excelente | Chaves substitutas e naturais críticas são testadas de forma consistente em toda a camada. |
| Integridade Analítica | 🟢 Excelente | O conjunto de testes reduz substancialmente riscos de dupla contagem, linhas órfãs e métricas divergentes. |

---

## Roadmap de Evolução

### Alta Prioridade

- Criar unit tests para `fact_order_items`, `fact_payments` e `fact_purchase_order_items`.
  - Benefício: isola fórmulas e regras de derivação complexas.
  - Impacto: alto, porque reduz regressões silenciosas em lógica de negócio.
  - Esforço estimado: médio.
- Adicionar testes de continuidade temporal em `dim_date`.
  - Benefício: valida spine diário sem lacunas e evita erros de calendário.
  - Impacto: alto para análises históricas e consistência temporal.
  - Esforço estimado: médio.
- Incluir reconciliação de agregação em fatos de vendas e compras.
  - Benefício: reduz risco de divergência entre fatos e cabeçalhos operacionais.
  - Impacto: alto para confiabilidade financeira.
  - Esforço estimado: médio.

### Média Prioridade

- Cobrir explicitamente a seleção determinística de endereço em `dim_customers`.
  - Benefício: prova a regra de priorização do endereço principal.
  - Impacto: médio.
  - Esforço estimado: médio.
- Validar coerência entre `returned_at`, `placed_at` e datas de pedido original em `fact_return_items`.
  - Benefício: reforça a auditoria de pós-venda.
  - Impacto: médio.
  - Esforço estimado: baixo a médio.
- Cobrir `reference_table` e `nk_reference_id` em `fact_stock_movements`.
  - Benefício: melhora a rastreabilidade operacional das movimentações.
  - Impacto: médio.
  - Esforço estimado: baixo.

### Baixa Prioridade

- Introduzir testes de formato para CPF, e-mail, telefone e CEP onde fizer sentido.
  - Benefício: melhora qualidade cadastral.
  - Impacto: baixo a médio.
  - Esforço estimado: baixo.
- Adicionar validações semânticas para campos descritivos sem domínio fechado, como `trade_name`, `brand_country` e `category_slug`.
  - Benefício: incrementa consistência do catálogo analítico.
  - Impacto: baixo.
  - Esforço estimado: baixo.

---

## Conclusão

A camada `marts` apresenta uma estratégia de testes madura para um projeto dbt em ambiente corporativo. O desenho atual prioriza o que é mais importante para Analytics Engineering: integridade referencial, unicidade, nulidade mínima, domínios fechados e validação de métricas derivadas.

Os pontos mais fortes estão nos fatos de negócio, que combinam generic tests com singular tests para validar regras financeiras, temporais e operacionais. As dimensões também estão bem protegidas, embora `dim_date` e algumas regras de seleção ou normalização ainda possam evoluir com validações mais finas.

Em resumo, a estratégia implementada oferece uma base confiável para exploração analítica, reduz risco de regressões e já atende bem a um cenário de auditoria e manutenção contínua.
