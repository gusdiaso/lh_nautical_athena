# Documentação de CI/CD: Deploy Automático no Databricks via Bitbucket

Esta documentação detalha a arquitetura e o funcionamento da nossa esteira de integração e entrega contínua (CI/CD). O processo utiliza o **Bitbucket Pipelines** e **Databricks Asset Bundles (DABs)** para garantir deploys seguros, automatizados e independentes de contas de usuários físicos.

---

## 1. Visão Geral da Arquitetura

Para garantir a segurança e seguir as melhores práticas de governança, separamos as responsabilidades do deploy em duas frentes:

- **O Entregador (Bitbucket Pipelines):** Atua do lado de fora do Databricks. Sua função é monitorar a branch principal, capturar o código atualizado, autenticar-se no Databricks via API e realizar o deploy da infraestrutura e dos códigos.
- **O Trabalhador (Service Principal):** É a entidade robô (`sp-prod-lh-nautical`) que existe dentro do Databricks. Ela se torna a proprietária (Owner) de todos os Jobs e Workflows em produção e é quem de fato executa o processamento dos dados.


---

## 2. A Service Principal de Produção

Todos os recursos de produção são executados sob a identidade da Service Principal definida em `databricks.yml`.

- **Nome da Entidade:** `sp-prod-lh-nautical`
- **Autenticação:** OAuth Machine-to-Machine (M2M).
- **Segurança:** A entidade possui apenas privilégios necessários para executar jobs e acessar o catálogo de produção.

---

## 3. Variáveis e Segredos (Bitbucket)

A autenticação da esteira ocorre através de variáveis de ambiente injetadas em tempo de execução. As credenciais nunca são expostas no código-fonte. Elas estão salvas no menu **Repository settings > Repository variables** no Bitbucket:

1.  `DATABRICKS_HOST`: A URL base do nosso workspace (`https://dbc-c4e046bc-37b5.cloud.databricks.com`). Compartilhada entre dev e prod, pois é o mesmo workspace.
2.  `DATABRICKS_CLIENT_ID_PROD`: O Application ID público da Service Principal de produção.
3.  `DATABRICKS_CLIENT_SECRET_PROD`: A chave secreta gerada no Databricks (esta variável está configurada como **Secured** no Bitbucket para garantir criptografia nos logs).

O step de deploy mapeia essas duas últimas para os nomes sem sufixo (`DATABRICKS_CLIENT_ID` / `DATABRICKS_CLIENT_SECRET`) que a CLI do Databricks espera por padrão, via `export` no início do script. O mesmo padrão se repete para dev — veja a tabela completa na seção 4.3.

---

## 4. Arquivos de Configuração

A automação depende de dois arquivos fundamentais na raiz do projeto:

### 4.1. `bitbucket-pipelines.yml` (A Esteira)

Instrui o Bitbucket sobre como preparar a máquina, instalar a CLI oficial do Databricks e disparar o comando de deploy. A imagem definida no topo do arquivo (`image: python:3.12`) vale para todos os pipelines do arquivo, inclusive este.

```yaml
image: python:3.12

pipelines:
  branches:
    main: # O pipeline é acionado automaticamente ao fazer merge na branch main
      - step:
          name: 'Deploy para Produção no Databricks'
          script:
            # 1. Mapeia as credenciais de prod para os nomes que a CLI do Databricks espera
            - export DATABRICKS_CLIENT_ID=$DATABRICKS_CLIENT_ID_PROD
            - export DATABRICKS_CLIENT_SECRET=$DATABRICKS_CLIENT_SECRET_PROD

            # 2. Instalação de dependências
            - apt-get update && apt-get install -y curl unzip

            # 3. Instalação da CLI do Databricks
            - curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh | sh

            # 4. Execução do deploy
            - databricks bundle deploy -t prod
            - databricks bundle run orchestrator_transform --target prod
```

### 4.2. `databricks.yml` (O Bundle)

Define a infraestrutura como código (IaC). O bloco `run_as` é crítico, pois garante que os recursos criados no Databricks pertençam à Service Principal e não a quem iniciou o commit.

```yaml
targets:
  prod:
    mode: production
    permissions:
      - group_name: lh_nautical_prod
        level: CAN_VIEW
    git:
      branch: main
    # Define a Service Principal como proprietária dos recursos
    run_as:
      service_principal_name: '1d6b3e3c-c04d-41e0-9883-ae8d467adcaf'
```

### 4.3. Pipeline de Pull Request (Validação)

Antes de qualquer merge na `main`, o Bitbucket Pipelines roda automaticamente em toda **Pull Request** três etapas de validação, usando o ambiente de **dev**:

1. **Lint (`sqlfluff`)**: instala as dependências, roda `dbt deps` e executa `sqlfluff lint` sobre `src/dbt/models`, validando estilo e convenções SQL contra o dialeto `sparksql` (via templater `dbt`).
2. **`dbt build` (dev)**: roda `dbt build --target dev`, que materializa seeds, models e snapshots e executa os testes de dados do dbt, na ordem do DAG — valida de verdade se o código funciona contra o warehouse, não só a sintaxe.
3. **Testes automatizados (`pytest`)**: autentica via OAuth M2M com a Service Principal de **dev** (`DATABRICKS_CLIENT_ID_DEV` / `DATABRICKS_CLIENT_SECRET_DEV`) e roda a suíte de testes em `tests/`, que abre uma sessão real via Databricks Connect (com fallback automático para serverless compute).

> **Sobre o `dbt build`:** como o target `dev` é compartilhado entre todo o time (e possivelmente jobs agendados), uma escrita concorrente em outra PR pode gerar um erro transitório `DELTA_METADATA_CHANGED`. O step tenta `dbt build --target dev` e, se falhar, roda `dbt retry --target dev` automaticamente — que reprocessa só os models que falharam, sem refazer a build inteira. Se mesmo assim falhar (erro persistente, não transitório), vale checar o log antes de simplesmente re-rodar o pipeline.

Essas etapas usam variáveis de repositório específicas de **dev**, mapeadas para os nomes que o dbt e o Databricks SDK esperam. Para referência, a tabela abaixo mostra o mesmo padrão usado no deploy de **prod** (seção 4.1):

| Variável no Bitbucket | Usada como | Onde é consumida |
|---|---|---|
| `DBT_HTTP_PATH` | `DBT_HTTP_PATH` | `profiles.yml` (compartilhada entre dev e prod) |
| `DBT_DATABRICKS_TOKEN_DEV` | `DBT_DATABRICKS_TOKEN` | `profiles.yml` (target `dev`) |
| `DATABRICKS_HOST` | `DATABRICKS_HOST` | Databricks SDK / Connect / CLI (compartilhada) |
| `DATABRICKS_CLIENT_ID_DEV` | `DATABRICKS_CLIENT_ID` | Databricks SDK / Connect (auth M2M, dev) |
| `DATABRICKS_CLIENT_SECRET_DEV` | `DATABRICKS_CLIENT_SECRET` | Databricks SDK / Connect (auth M2M, dev) |
| `DBT_DATABRICKS_TOKEN_PROD` | `DBT_DATABRICKS_TOKEN_PROD` | `profiles.yml` (target `prod`, já sem remapeamento) |
| `DATABRICKS_CLIENT_ID_PROD` | `DATABRICKS_CLIENT_ID` | CLI do Databricks (auth M2M, deploy de prod) |
| `DATABRICKS_CLIENT_SECRET_PROD` | `DATABRICKS_CLIENT_SECRET` | CLI do Databricks (auth M2M, deploy de prod) |

> O gate de qualidade da `main` é feito na própria PR: a branch é protegida (sem commit direto) e o merge só é permitido com o pipeline de PR (lint + build + testes) aprovado. Por isso o pipeline da `main` não repete essas etapas — ele só faz o deploy.

### 4.3.1. Disparo manual em qualquer branch

Existe também um pipeline `custom` chamado `validar-qualidade`, que roda as mesmas três etapas (lint + `dbt build` + testes) sob demanda, em qualquer branch — útil para validar uma branch específica sem precisar abrir uma PR. Para disparar:

1. No Bitbucket, acesse **Pipelines** (ou **Branches > ... > Run pipeline**).
2. Clique em **Run pipeline**.
3. Escolha a branch desejada e selecione o pipeline customizado `validar-qualidade`.

---

## 5. Permissões de Dados (Unity Catalog)

Para que os Jobs rodem com sucesso, a Service Principal precisa ter permissão explícita para interagir com o catálogo de produção. O acesso foi concedido no Data Explorer do Databricks:

- Catálogo: prod_lh_nautical
- Grants Concedidos à Entidade: USE CATALOG, USE SCHEMA, SELECT (leitura) e MODIFY (gravação) nos schemas necessários.

## 6. Fluxo de Trabalho de Desenvolvimento

Com a esteira totalmente configurada, o processo diário de desenvolvimento e deploy segue o fluxo padrão do Git:

1. O desenvolvedor escreve e testa seus scripts (Python, SQL) localmente ou em ambiente de desenvolvimento.

2. Atualiza os arquivos no repositório local e realiza o commit:

```bash
git add .
git commit -m "feat: adiciona nova tabela bronze de clientes"
```

3. Envia as alterações para o repositório remoto na branch em que você está trabalhando:

```bash
git push origin <branch>
```

4. Assim que abrir o PR e ele for mergeado com a main, o Bitbucket Pipelines detecta a alteração, inicia a máquina virtual, autentica via OAuth e realiza o bundle deploy. Em poucos minutos, a alteração estará disponível e pronta para uso no Workspace do Databricks.

> **Nota:** O pipeline atual faz deploy do bundle e executa o job `orchestrator_transform` na produção, que coordena extração, validação, column masking e transformação dbt de forma sequencial, com agendamento para as 23:00 BRT.
