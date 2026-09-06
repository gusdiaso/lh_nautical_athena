# MVP do RAG documental

## Escopo

O RAG responde somente sobre documentacao versionada do projeto LH Nautical. Ele nao consulta tabelas Bronze, Silver ou Gold, nao gera SQL e nao retorna valores atuais de vendas, faturamento, estoque ou outros dados numericos do Data Warehouse.

## Estado atual

O modulo `src/analytics_ai/rag_documents.py` implementa a etapa offline de preparacao:

- allowlist explicita de arquivos aprovados;
- leitura de Markdown, TXT e HTML;
- remocao de `script`, `style`, `head`, `nav`, `footer` e `noscript` do HTML;
- mascaramento de tokens, senhas, chaves e e-mails;
- metadados de origem, tipo, secao, data de alteracao e hash;
- chunking configuravel, iniciando com 800 caracteres e overlap de 80;
- IDs estaveis para deduplicacao e atualizacao idempotente.

O modulo `src/analytics_ai/rag_prompt.py` implementa os limites da geracao:

- deteccao de perguntas sobre dados numericos do Data Warehouse;
- contexto delimitado com nome do arquivo e secao;
- prompt restritivo para respostas fundamentadas e citaveis.

O modulo `src/analytics_ai/rag_databricks.py` implementa a fronteira com o Databricks:

- validacao de identificadores `catalog.schema.table`;
- conversao dos chunks para linhas com schema explicito;
- escrita da tabela Delta documental com CDF opcional;
- criacao de indice Delta Sync por cliente Vector Search injetavel;
- retrieval hibrido com filtros e bloqueio antes da consulta ao indice;
- erro explicito quando `databricks-ai-search` nao esta instalado.

## Dependencias

`databricks-ai-search` nao deve ser adicionado ao `requirements.txt` principal
neste momento: a versao atual do SDK exige `protobuf < 6`, enquanto o dbt do
projeto exige `protobuf >= 6`. Instale o SDK somente no runtime Databricks do
job/notebook RAG, com uma imagem e conjunto de dependencias validados para esse
ambiente. O ambiente local deve continuar com `pip check` sem conflitos.

Os testes offline podem ser executados sem Databricks Connect:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_rag_documents -v
```

## Proxima integracao no Databricks

1. Publicar os documentos aprovados em um Unity Catalog Volume. **Concluido em dev.**
2. Confirmar catalogo, schema, endpoint de embedding, endpoint LLM e permissao minima da identidade de execucao. **Concluido em dev:** `dev_lh_nautical.rag`, `databricks-bge-large-en` e `databricks-meta-llama-3-3-70b-instruct`.
3. Converter os objetos `Chunk` para uma tabela Delta exclusiva do RAG. **Concluido:** `dev_lh_nautical.rag.document_chunks`, com 224 chunks e CDF habilitado.
4. Instalar `databricks-ai-search` no runtime aprovado e criar um indice Delta Sync com pipeline `TRIGGERED`. **Concluido em dev:** indice Hybrid pronto com os chunks documentais.
5. Usar `retrieve_context` com busca hibrida, filtros e `top-k` entre 3 e 5. **Concluido na demonstracao end-to-end.**
6. Bloquear perguntas numericas antes de chamar o LLM.
7. Validar 15 a 20 perguntas do Golden Dataset, incluindo perguntas sem resposta, prompt injection e consultas que devem ser recusadas. **Pendente.**

## Seguranca

Antes de publicar o corpus, revogue e rotacione qualquer token que tenha sido exposto no ambiente local ou no historico do Git. O RAG deve receber acesso somente ao Volume, tabela Delta e indice documentais. O acesso de leitura ao Data Warehouse deve permanecer fora da identidade usada pelo RAG.

Relatorios e documentos de planejamento que repetem informacoes devem entrar somente depois de receberem versao, data e status de validade. Artefatos em `target/`, `dbt_packages/`, `.databricks/`, `logs/` e `.env` nunca devem ser indexados.
