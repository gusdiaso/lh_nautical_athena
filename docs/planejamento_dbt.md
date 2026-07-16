# Planejamento do Projeto Lakehouse Nautical

---

## Cronograma

1. Configuração do dbt: até 08/07
2. Staging e intermediate: até 13/07 (máximo 16/07)
3. Marts: até 22/07 ou 23/07

### Fase 1: Configuração do dbt (05/07 - 08/07)

| Dia | Entregável | Responsável |
|-----|------------|-------------|
| 07/07 | Configuração do profiles.yml e estrutura do projeto dbt | Gustavo |
| 07/07 | Configuração das fontes (sources) no dbt | Gustavo |
| 08/07 | Testes de conexão e documentação básica | Gustavo |
| 08/07 | Validação e ajustes finais da configuração | Gustavo |


### Fase 2: Staging e Intermediate (09/07 - 13-16/07)

#### Danilo Cerqueira
| Dia | Entregável |
|-----|------------|
| 09-10/07 | Staging: orders, employees, customers, payments, goods_receipts, product_suppliers, categories, brands |
| 11-12/07 | Intermediate: orders, employees, customers, payments, goods_receipts, product_suppliers, categories, brands |
| 13/07 | Validação dos models |

#### Fernanda Dittert
| Dia | Entregável |
|-----|------------|
| 09-10/07 | Staging: stock_movements, returns, addresses, product_variants, suppliers, stock_levels, variant_attribute_values, exchange_rates |
| 11-12/07 | Intermediate: stock_movements, returns, addresses, product_variants, suppliers, stock_levels, variant_attribute_values, exchange_rates |
| 13/07 | Validação dos models |

#### Gustavo Dias
| Dia | Entregável |
|-----|------------|
| 09-10/07 | Staging: purchase_orders, order_items, return_items, products, locations, purchase_order_items, goods_receipt_items, attributes |
| 11-12/07 | Intermediate: purchase_orders, order_items, return_items, products, locations, purchase_order_items, goods_receipt_items, attributes |
| 13/07 | Validação dos models |

### Fase 3: Marts (14-17/07 - 23/07)

#### Em planejamento
...

---
---

## Como Funciona Este Projeto

### Onde Queremos Chegar

Nosso objetivo e transformar dados brutos (Bronze) em informacoes prontas para analise (Gold). Pense assim:

- **Bronze** = Dados crus, como chegam do sistema
- **Staging** = Copia organizada dos dados brutos
- **Intermediate** = Dados limpos, padronizados e validados
- **Marts** = Dados prontos para gerar relatorios e dashboards

### Por Que Usamos 4 Camadas?

Muitas pessoas perguntam: "por que tanta camada?". A resposta e: **por organizacao e seguranca**.

**Bronze** = Onde os dados chegam. Nao mexemos aqui.

**Staging** = Fazemos uma copia organizada dos dados. E como fazer uma fotocopia antes de editar. Se algo der errado, a copia original continua segura. Aqui so mudamos nomes de colunas e removemos colunas de controle (_ingested_at, _source_path).

**Intermediate** = Aqui fazemos a limpeza real: removemos duplicatas, corrigimos valores, padronizamos formatos e validamos regras de negocio.

**Marts** = Aqui montamos o modelo dimensional (tabelas prontas para consulta) com dimensoes e fatos.

### Como o Projeto é Organizado (Modularizacao)

Imagina que cada tarefa grande e dividida em partes menores e faceis de entender:

**1. Dominios de Negocio**
Cada area do negocio e um "modulo" separado:
- Referencias (marcas, categorias, localizacoes)
- Clientes
- Produtos
- Pedidos de Venda
- Pedidos de Compra
- Estoque
- Devolucoes
- Cambio

**2. Models com Nomes Claros**
Cada arquivo SQL tem um nome que diz exatamente o que faz:
- `stg_*` = Staging (copia organizada)
- `int_*` = Intermediate (limpeza e validacao)
- `dim_*` = Dimensao (informacoes descritivas)
- `fact_*` = Fato (numeros e metricas)

**3. Dependencias Organizadas**
Os models sao construidos na ordem certa:
1. Primeiro o Staging (copia organizada)
2. Depois o Intermediate (limpeza)
3. Por ultimo os Marts (modelo dimensional)

### O Que Sao Macros e Jinja?

**Jinja** e uma linguagem de template que o dbt usa para deixar o codigo mais inteligente. Em vez de escrever a mesma coisa varias vezes, voce cria uma "formula" reutilizavel.

**Macro** e como uma "funcao" que voce cria para automatizar tarefas repetitivas.

**Exemplo Simples:**

Em vez de escrever em cada model:
```sql
SELECT
    id AS customer_id,
    name AS customer_name
FROM bronze.customers
WHERE id IS NOT NULL
```

Voce cria uma macro que faz isso automaticamente:
```sql
{{ limpar_colunas('id', 'name', 'customer_id', 'customer_name') }}
```

**Como Vamos Usar no Projeto:**
- Macros para padronizar nomes de colunas
- Macros para gerar chaves substitutas (surrogate keys)
- Macros para testes de qualidade
- Jinja para criar logicas condicionais (ex: "se currency for USD, usar cambio")

### O Que Sao Testes e Testes Singulares?

**Testes** sao verificacoes automaticas que garantem que os dados estao corretos.

**Tipos de Teste:**
1. **Nao nulo** - Coluna obrigatoria nao pode estar vazia
2. **Unico** - Nao pode ter valores repetidos
3. **Relacionamento** - Valores devem existir na tabela referenciada
4. **Valores aceitos** - So pode ter valores de uma lista pre-definida

**Teste Singular** e um teste especifico criado para uma regra de negocio. Exemplo:
- "Nenhum pedido pode ter valor negativo"
- "Todo cliente deve ter pelo menos um endereco"
- "Cotacao de cambio nao pode ser zero"

**Como é Feito:**
Cada model tem seu teste. Se algum teste falhar, o dbt para a execucao e mostra o erro. Isso garante que so dados chegam ao cliente final se estiverem corretos.


---

## 1. Visao Geral do Projeto

### Estrutura Atual

| Camada | Catalogo | Schema | Status |
|--------|----------|--------|--------|
| Bronze | `dev_lh_nautical` / `prod_lh_nautical` | `bronze` | Implementado |
| Staging | `dev_lh_nautical` / `prod_lh_nautical` |  | Planejado |
| Intermediate | `dev_lh_nautical` / `prod_lh_nautical` | `silver` | Planejado |
| Marts | `dev_lh_nautical` / `prod_lh_nautical` | `gold` | Planejado |

### Tabelas Bronze Existentes (24 tabelas)

**Referencia (5):** categories, brands, locations, attributes, employees

**Clientes (2):** customers, addresses

**Fornecedores (1):** suppliers

**Produtos (4):** products, product_variants, variant_attribute_values, product_suppliers

**Pedidos de Compra (4):** purchase_orders, purchase_order_items, goods_receipts, goods_receipt_items

**Pedidos de Venda (3):** orders, order_items, payments

**Devolucoes (2):** returns, return_items

**Estoque (2):** stock_levels, stock_movements

**Cambio (1):** exchange_rates

### Modelo Dimensional (Star Schema)

O modelo segue o padrao Star Schema com **6 dimensoes** e **6 tabelas de fato**, conforme descrito em `docs/star_schema.md`.

**Flexibilidade:** O modelo não é imutável. Caso seja identificado algum ponto de melhoria, por favor trazer ao grupo.

---

## 2. Tabela de Cambio - Uso na Camada Intermediate/Marts

### Origem dos Dados

A tabela `exchange_rates` ja esta sendo ingerida na Bronze via job `extract_exchange_rates`, que busca cotacoes PTAX do Banco Central do Brasil. Ela contem cotacoes de compra e venda para **USD** (Dolar) e **EUR** (Euro).

### Onde sera Usada

A tabela de cambio sera utilizada nas seguintes situacoes:

1. **int_purchase_order** - Para usar o campo `currency` (moeda do pedido de compra) para criar a coluna de cotação da moeda no dia do pedido.
2. **fact_purchase_order_items** - Para usar a coluna de cotação da moeda no dia do pedido para fazer o calculo real.


### Regras de Negocio para Cambio

- **Conversao:** Usar `exchange_rate_sell` para converter valores de moeda estrangeira para BRL
- **Data de referencia:** Usar a cotacao do dia da transacao
- **Caso nao exista cotacao no dia:** Usar a cotacao do dia util anterior mais proximo

---

## 3. Camada Staging

**Pense assim:** O Staging é a "portaria" dos dados. Os dados chegam da Bronze do jeito que o sistema mandou, bagunçados, com nomes estranhos, cheios de lixo técnico. O Staging não inventa nada, só organiza: tira o que não presta, dá nomes bonitos, e aponta quem é a chave de cada linha. É tipo receber uma mudança: você separa as caixas por cômodo, mas ainda não abriu nenhuma.

| Regra | O que fazer |
|-------|-------------|
| **Filtrar** | Tire fora colunas que só interessam pro sistema, não pro negócio — metadados, controles internos, lixo técnico |
| **Renomear** | Dê nomes claros e em inglês (usando snake_case). Se veio `cotacaoCompra`, vira `exchange_rate_buy` |
| **PKs** | Identifique e deixe explícito qual coluna (ou conjunto delas) identifica cada linha de forma única |
| **Nomenclatura** | Use nomes que qualquer pessoa do time entende de primeira. Nada de abreviações estranhas ou nomes genéricos |

---

## 4. Camada Intermediate

**Pense assim:** A Intermediate é o "controle de qualidade". O Staging organizou as caixas, agora você abre cada uma e confere peça por peça. Tem parafuso repetido? Joga fora. Veio sem manual? Tenta achar na internet. Peça amassada? Endireita. Só passa pra frente o que está em perfeito estado. É aqui que o dado ganha confiança pra ser usado.

| Regra | O que fazer |
|-------|-------------|
| **Dedup** | Se veio repetido, fique só com um. Use o mais recente ou o primeiro |
| **Tratar nulos** | Antes de descartar, veja se dá pra preencher, olhando outra tabela, chutando um padrão, ou perguntando pro time. Só jogue fora se não tiver jeito |
| **Validar FKs** | Confira se os IDs que você recebeu realmente existem na tabela de referência. |
| **Padronizar enums** | Garanta que valores tipo "Ativo", "ativo", "ATIVO" virem tudo a mesma coisa. Idem para status, tipo de pessoa, moeda |
| **Corrigir valores** | Se um valor claramente está errado (preço negativo, quantidade zero), corrija com uma regra de negócio. Não passe o problema pra frente |
| **Manter o grão** | Não misture tabelas nem resuma dados. Se o staging veio com 1 linha por pedido, a Intermediate sai com 1 linha por pedido, só que limpo |
| **Tipar** | Dinheiro é número decimal, data é data, texto é texto. Cada coisa no seu tipo certo |
| **Testar** | Coloque provas de que a limpeza funcionou, campos obrigatórios preenchidos, sem duplicatas, valores dentro do esperado. Faça testes! |

---

## 5. Camada Marts

**Pense assim:** O Marts é a "loja arrumada". A Intermediate deixou tudo limpo e separado, agora você monta o estoque nas prateleiras (dimensões) e organiza os preços nas gôndolas (fatos). O analista de BI entra na loja, puxa o que precisa e sai com o relatório pronto. Se a loja estiver bagunçada, ele não consegue achar nada. Se estiver bem montada, ele encontra tudo em segundos.

| Regra | O que fazer |
|-------|-------------|
| **Juntar** | Aqui você junta as tabelas da Intermediate formando o modelo dimensional. Cada dimensão vira uma tabela descritiva, cada fato vira uma tabela de métricas |
| **Criar chaves** | Gere uma chave substituta (sk_*) para cada dimensão usando hash. O Marts não conversa mais com IDs do sistema, só com essas chaves |
| **Enriquecer** | Na dimensão, traga junto tudo que descreve a entidade — se é cliente, vem nome, CPF, endereço, telefone. Tudo que ajuda a entender "quem é esse" |
| **Calcular** | No fato, faça as contas. Aqui sim você multiplica preço x quantidade, aplica imposto, calcula total. A Intermediate só limpou, quem calcula é o Marts |
| **Conectar** | Ligue dimensões e fatos pelas chaves substitutas. Um fato pode ter sk_date, sk_product, sk_customer — cada uma apontando pra sua dimensão |
| **Negar agregacão prematura** | Mantenha o grão mais fino possível. Se o usuário quiser resumo, ele faz na ferramenta de BI. Seu trabalho é entregar o dado mais detalhado que fizer sentido |
| **Testar** | Verifique se as chaves substitutas são únicas e não nulas, e se os relacionamentos entre fato e dimensão estão intactos — nenhum pedido órfão |
| **Pensar no BI** | Modele pensando em como o analista vai consumir. Dimensão é o "filtro" e "linha do relatório". Fato é o "valor" e o "número". Tabela bem modelada = dashboard simples |

---

## 6. Testes e Qualidade de Dados

**Pense assim:** Teste é o "extintor de incêndio" que você instala antes do fogo começar. Não adianta fazer um data pipeline lindo se ninguém confia no número que sai dele. Cada teste é uma promessa: "se esse teste passar, essa coluna está boa". Se o teste quebrar, o pipeline para e alguém olha, é melhor isso do que o cliente tomar decisão com dado errado.

| Regra | O que fazer |
|-------|-------------|
| **Testar cedo** | Teste já no Staging e Intermediate. Não espere o dado chegar no Marts pra descobrir que veio errado. Quanto antes achar o problema, mais barato ele é de consertar |
| **Cada camada testa uma coisa** | Staging testa se a cópia veio completa (nulos, chaves). Intermediate testa se a limpeza funcionou (FKs válidas, valores padronizados). Marts testa se o modelo está íntegro (relacionamentos, chaves substitutas) |
| **Priorize o crítico** | Nem tudo precisa de teste. Foque no que quebra o negócio: PK nula = dado perdido. FK inválida = relatório errado. Valor financeiro nulo = fechamento contábil incorreto |
| **Teste é prova, não enfeite** | Cada teste existe porque alguém vai sofrer se ele falhar. Se você não sabe por que um teste existe, talvez ele não seja necessário |
| **Documente riscos** | O time precisa saber o que é incerto antes de confiar no dado |
| **Trate o ponto em aberto como dívida** | Toda pendência não resolvida é um problema futuro. Priorize desbloquear com o time o que impede o avanço |

## 7. Documente o processo

**Pense assim:** Documentação é o "bilhete pra você do futuro". Daqui 3 meses, quando um teste quebrar de madrugada ou um novo estagiário entrar no time, a documentação é o que salva. Se não está escrito, não existe. Seu eu do futuro vai agradecer cada linha de documentação que você escreveu hoje.

| Regra | O que fazer |
|-------|-------------|
| **Documente enquanto faz** | Não deixe pra depois. Enquanto o raciocínio está fresco, escreva 2 linhas explicando o porquê de cada decisão. "Depois" vira "nunca" |
| **Explique o porquê, não o o quê** | O código já mostra o que está sendo feito. A documentação deve responder *por que* foi feito assim. Ex: "Filtramos pedidos cancelados porque o sistema ERP não os exclui, só marca status" |
| **Use o dbt docs** | O próprio dbt gera documentação automática dos modelos e colunas. Aproveite: coloque descrição em cada model e cada coluna. É trabalho único que paga juros compostos |
| **Mantenha o planejamento vivo** | Este documento que estamos construindo não é para ser engavetado. Atualize riscos, pendências, decisões. Se mudou a regra de câmbio, atualiza aqui |
| **Pense no próximo** | A pessoa que vai dar manutenção nisso pode ser você daqui 6 meses. Ou um estagiário perdido. Facilite a vida dela, e a sua |
| **Versionamento é documentação** | Mensagens de commit claras também documentam. "fix: trata exchange_rate = 0 buscando dia útil anterior" é documentação viva no git |

---

## Apendice: Diagrama de Dependencias

### Camada Staging (24 models)

```
Fontes Bronze
    |
    +-- stg_brands
    +-- stg_categories
    +-- stg_locations
    +-- stg_attributes
    +-- stg_employees
    +-- stg_exchange_rates
    +-- stg_customers
    +-- stg_addresses
    +-- stg_suppliers
    +-- stg_products
    +-- stg_product_variants
    +-- stg_variant_attribute_values
    +-- stg_product_suppliers
    +-- stg_orders
    +-- stg_order_items
    +-- stg_payments
    +-- stg_purchase_orders
    +-- stg_purchase_order_items
    +-- stg_goods_receipts
    +-- stg_goods_receipt_items
    +-- stg_stock_levels
    +-- stg_stock_movements
    +-- stg_returns
    +-- stg_return_items
```

### Camada Intermediate (24 models)

```
Camada Staging
    |
    +-- int_brands
    +-- int_categories
    +-- int_locations
    +-- int_attributes
    +-- int_employees
    +-- int_exchange_rates
    +-- int_customers
    +-- int_addresses
    +-- int_suppliers
    +-- int_products
    +-- int_product_variants
    +-- int_variant_attribute_values
    +-- int_product_suppliers
    +-- int_orders
    +-- int_order_items
    +-- int_payments
    +-- int_purchase_orders
    +-- int_purchase_order_items
    +-- int_goods_receipts
    +-- int_goods_receipt_items
    +-- int_stock_levels
    +-- int_stock_movements
    +-- int_returns
    +-- int_return_items
```

### Camada Marts (13 models)

```
Camada Intermediate
    |
    +-- dim_date
    +-- dim_customers
    +-- dim_products
    +-- dim_employees
    +-- dim_suppliers
    +-- dim_locations
    |
    +-- fact_order_items
        fact_payments
        fact_purchase_order_items
        fact_goods_receipt_items
        fact_stock_movements
        fact_return_items
```

---

## Legenda de Nomenclatura

| Prefixo | Camada | O Que Faz |
|---------|--------|-----------|
| `stg_*` | Staging | Copia organizada da Bronze (renomeia colunas) |
| `int_*` | Intermediate | Limpa e valida dados do Staging |
| `dim_*` | Marts | Dimensoes (informacoes descritivas) |
| `fact_*` | Marts | Tabelas de fato (numeros e metricas) |
| `sk_*` | Marts | Chave substituta (surrogate key) |
| `nk_*` | Marts | Chave natural (natural key) |

---

## Convenções de Código SQL

### Leading Comma

O projeto adota a convenção **leading comma** para formatação de queries SQL. Cada vírgula é colocada no **início** da linha, não no final.

**Exemplo:**

```sql
-- ✅ CORRETO (leading comma)
SELECT
    order_id
    , customer_id
    , order_date
    , total_amount
FROM int_orders
WHERE status = 'completed'

-- ❌ ERRADO (trailing comma)
SELECT
    order_id,
    customer_id,
    order_date,
    total_amount
FROM int_orders
WHERE status = 'completed'
```

**Vantagens:**
- **Git-friendly**: Ao adicionar ou remover colunas, o diff mostra apenas a linha alterada
- **Revisão facilitada**: Cada coluna fica em sua própria linha, tornando o código mais legível
- **Consistência**: Todo o time segue o mesmo padrão, evitando debates sobre formatação

**Regras:**
1. Coloque a vírgula no início da linha, alinhada com o nome da coluna
2. Uma coluna por linha
