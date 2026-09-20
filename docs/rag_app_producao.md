# Aplicação RAG em produção

Este documento registra a configuração versionável da aplicação RAG documental publicada no Databricks. Credenciais, tokens, conteúdo dos documentos e o estado dos recursos remotos não devem ser armazenados no repositório.

## Aplicação

- Nome: `lh-nautical-rag-prod`
- Workspace: `https://dbc-c4e046bc-37b5.cloud.databricks.com`
- Caminho compartilhado do código de release: `/Workspace/Shared/lh-nautical-rag-prod/release-001`
- URL: `https://lh-nautical-rag-prod-7474644871952143.aws.databricksapps.com`
- Comando de inicialização: `streamlit run apps/rag_chat/app.py --server.address 0.0.0.0 --server.headless true`

A definição local da aplicação está em [`apps/rag_chat/app.yaml`](../apps/rag_chat/app.yaml). O arquivo usa bindings para que os nomes dos recursos sejam resolvidos pelo Databricks Apps, sem embutir segredos no código:

- `documentary-index`: índice vetorial de produção;
- `generation-endpoint`: endpoint de geração configurado no workspace.

## Recursos de produção

Os recursos abaixo pertencem ao catálogo `prod_lh_nautical` e são administrados no workspace:

- esquema: `prod_lh_nautical.rag`;
- volume de documentos: `prod_lh_nautical.rag.documents`;
- tabela de chunks: `prod_lh_nautical.rag.document_chunks`;
- índice vetorial: `prod_lh_nautical.rag.document_chunks_index`;
- endpoint de consulta do índice: `rag-documents-prod`;
- endpoint de geração: `databricks-meta-llama-3-3-70b-instruct`.

As permissões de leitura e consulta devem ser aplicadas pelos scripts em [`resources/security`](../resources/security), seguindo o princípio do menor privilégio. A aplicação deve receber apenas os bindings necessários para consultar o índice e o endpoint de geração.

## Publicação

Execute a publicação autenticado no workspace correto, usando um perfil local do Databricks. O perfil não deve ser commitado:

```bash
databricks auth login \
  --host https://dbc-c4e046bc-37b5.cloud.databricks.com \
  --profile <perfil-do-workspace>

databricks apps list --profile <perfil-do-workspace>
databricks apps get lh-nautical-rag-prod --profile <perfil-do-workspace>
```

Depois de publicar uma nova versão, confirme no retorno do comando que o estado do deployment é `SUCCEEDED` e que o estado do compute é `ACTIVE`. A URL da aplicação pode redirecionar para autenticação do workspace; isso é esperado para uma aplicação interna.

## Verificações após a publicação

1. Abra a aplicação pelo menu **Apps** ou pela URL registrada acima.
2. Faça uma pergunta cuja resposta esteja nos documentos permitidos.
3. Confirme que a resposta exibe as fontes retornadas pelo índice.
4. Consulte os health checks e a avaliação existentes antes de promover mudanças de prompt, modelo ou permissões.

O índice vetorial pode permanecer em sincronização após a primeira publicação. Nesse período a aplicação pode abrir normalmente, mas algumas consultas podem aguardar a atualização do índice.

## Escopo do PR

Este PR versiona somente documentação e código/configuração já presentes no repositório. Não inclui `.env`, credenciais, caches, logs, CSVs, conteúdo dos documentos ou alterações feitas diretamente nos recursos remotos do Databricks.
