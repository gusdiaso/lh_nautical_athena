# Camada Marts - Guia de Leitura

## Objetivo

A camada Marts concentra os modelos analíticos finais do projeto LH Nautical. Ela foi desenhada para consumo por BI, análises exploratórias e validação operacional. A camada é construída a partir dos intermediates, que por sua vez são derivados das fontes de dados.

## Escopo

Este conjunto contém os seguintes modelos:

- `dim_date`
- `dim_brands`
- `dim_categories`
- `dim_customers`
- `dim_employees`
- `fact_orders`
- `fact_payments`
- `fact_goods_receipts`
- `fact_product_suppliers`

## Como Ler o Modelo

As dimensões descrevem o contexto das análises e usam chaves substitutas com prefixo `sk_`. As fatos carregam os eventos de negócio e mantêm o menor grão útil para análise.

Nem todo atributo descritivo segue o padrão `sk_`/`nk_`. Campos de domínio vindos da origem, como `brand_name` e `category_name`, preservam a nomenclatura funcional para facilitar leitura humana e rastreabilidade com o dado original.

- `dim_date` organiza a leitura temporal e permite agrupar por dia, mês, ano e fim de semana.
- `dim_brands`, `dim_categories`, `dim_customers` e `dim_employees` servem como eixo descritivo das análises.
- `fact_orders` é o ponto de partida para pedidos de venda.
- `fact_payments` vincula pagamentos aos pedidos.
- `fact_goods_receipts` representa os recebimentos de mercadoria.
- `fact_product_suppliers` documenta o relacionamento entre produto e fornecedor.

## Decisões De Projeto

### Dimensão Calendário

A dimensão calendário foi incluída para facilitar filtros, agrupamentos e análises temporais sem depender de funções de data espalhadas pelos dashboards.

### Chaves Substitutas

As dimensões usam `sk_*` para padronizar o relacionamento com as fatos. Isso evita acoplamento com identificadores naturais e simplifica evoluções futuras.

### Granularidade

O desenho foi mantido no nível mais próximo do evento disponível nos intermediates atuais. Quando o modelo de negócio tiver uma tabela de detalhe mais rica, a fato correspondente pode ser refinada sem quebrar a estrutura base.

## Dependências

As marts do Danilo consomem diretamente os intermediates já validados:

- `int_brands`
- `int_categories`
- `int_customers`
- `int_employees`
- `int_orders`
- `int_payments`
- `int_goods_receipts`
- `int_product_suppliers`

## Como Validar

Para validar a camada localmente, use:

```bash
c:/Users/Usuario/grupo_5/.venv/Scripts/python.exe -m dbt.cli.main compile --select marts
```

Para checagem de qualidade após a geração dos modelos, rode também os testes do dbt no ambiente do projeto.

## Observações

Este documento é uma visão prática para leitura humana. A documentação técnica complementar fica nas descrições dos modelos e colunas do dbt, em `src/dbt/models/marts/marts.yml`.