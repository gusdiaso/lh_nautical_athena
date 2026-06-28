# Documentação de CI/CD: Deploy Automático no Databricks via Bitbucket

Esta documentação detalha a arquitetura e o funcionamento da nossa esteira de integração e entrega contínua (CI/CD). O processo utiliza o **Bitbucket Pipelines** e **Databricks Asset Bundles (DABs)** para garantir deploys seguros, automatizados e independentes de contas de usuários físicos.

---

## 1. Visão Geral da Arquitetura

Para garantir a segurança e seguir as melhores práticas de governança, separamos as responsabilidades do deploy em duas frentes:

- **O Entregador (Bitbucket Pipelines):** Atua do lado de fora do Databricks. Sua função é monitorar a branch principal, capturar o código atualizado, autenticar-se no Databricks via API e realizar o deploy da infraestrutura e dos códigos.
- **O Trabalhador (Service Principal):** É a entidade robô (`sp-prod-lh-nautical`) que existe dentro do Databricks. Ela se torna a proprietária (Owner) de todos os Jobs e Workflows em produção e é quem de fato executa o processamento dos dados.

---

## 2. A Service Principal de Produção

Todos os recursos de produção são executados sob a identidade da Service Principal configurada no workspace.

- **Nome da Entidade:** `sp-prod-lh-nautical`
- **Autenticação:** OAuth Machine-to-Machine (M2M).
- **Segurança:** A entidade possui apenas privilégios de Workspace e Databricks SQL. Seguindo o princípio do menor privilégio, ela **não possui acesso de administrador (Admin)**.

---

## 3. Variáveis e Segredos (Bitbucket)

A autenticação da esteira ocorre através de variáveis de ambiente injetadas em tempo de execução. As credenciais nunca são expostas no código-fonte. Elas estão salvas no menu **Repository settings > Repository variables** no Bitbucket:

1.  `DATABRICKS_HOST`: A URL base do nosso workspace de produção (`https://dbc-c4e046bc-37b5.cloud.databricks.com`).
2.  `DATABRICKS_CLIENT_ID`: O Application ID público da Service Principal.
3.  `DATABRICKS_CLIENT_SECRET`: A chave secreta gerada no Databricks (esta variável está configurada como **Secured** no Bitbucket para garantir criptografia nos logs).

---

## 4. Arquivos de Configuração

A automação depende de dois arquivos fundamentais na raiz do projeto:

### 4.1. `bitbucket-pipelines.yml` (A Esteira)

Instrui o Bitbucket sobre como preparar a máquina, instalar a CLI oficial do Databricks e disparar o comando de deploy.

```yaml
image: ubuntu:22.04

pipelines:
  branches:
    main: # O pipeline é acionado automaticamente ao fazer merge na branch main
      - step:
          name: 'Deploy para Produção no Databricks'
          script:
            # 1. Instalação de dependências
            - apt-get update && apt-get install -y curl unzip

            # 2. Instalação da CLI do Databricks
            - curl -fsSL https://raw.githubusercontent.com/databricks/setup-cli/main/install.sh | sh

            # 3. Execução do deploy (as variáveis de ambiente são injetadas nativamente)
            - databricks bundle deploy -t prod
```

4.2. databricks.yml (O Bundle)
Define a infraestrutura como código (IaC). O bloco run_as é crítico, pois garante que os recursos criados no Databricks pertençam à Service Principal e não a quem iniciou o commit.

### 4.2. `databricks.yml` (O Bundle)

Define a infraestrutura como código (IaC). O bloco `run_as` é crítico, pois garante que os recursos criados no Databricks pertençam à Service Principal e não a quem iniciou o commit.

```yaml
targets:
  prod:
    mode: production
    workspace:
      host: https://dbc-c4e046bc-37b5.cloud.databricks.com
    # Define a Service Principal como proprietária dos recursos
    run_as:
      service_principal_name: '<COLOQUE-O-APPLICATION-ID-AQUI>'
```

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
