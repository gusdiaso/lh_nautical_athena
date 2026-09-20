# Interface interna da RAG

Protótipo Streamlit para uso supervisionado. Não comprova qualidade da RAG nem
substitui a avaliação smoke/full. Confira as fontes. Nenhum recurso remoto é
criado pelo código da interface.

## Execução local

Na raiz do repositório, use um ambiente separado do dbt/Databricks Connect:

```bash
python3 -m venv /tmp/lh-rag-app-venv
/tmp/lh-rag-app-venv/bin/python -m pip install -r apps/rag_chat/requirements.txt
databricks auth login --host https://dbc-c4e046bc-37b5.cloud.databricks.com --profile lh-nautical-developers
DATABRICKS_CONFIG_PROFILE=lh-nautical-developers /tmp/lh-rag-app-venv/bin/python -m streamlit run apps/rag_chat/app.py --server.address 127.0.0.1
```

Abra a URL localhost exibida pelo Streamlit. A página pode abrir sem login;
perguntas documentais permitidas consultam os endpoints reais e consomem quota.
Recusas prévias e entradas inválidas não inicializam clientes remotos.
O login é feito manualmente; não coloque credenciais em arquivos do projeto.

Configurações opcionais no backend: `RAG_INDEX_NAME`, `RAG_LLM_ENDPOINT`.
Os padrões são o índice documental dev e o Llama configurado na RAG atual.
O adaptador SDK resolve o índice pelo nome completo; não precisa selecionar o
endpoint de busca separadamente. Usa autenticação unificada para CLI local e
OAuth da identidade da App, com o cliente OpenAI autenticado pelo SDK. A fábrica get_open_ai_client do SDK
está depreciada, mas mantém renovação OAuth por requisição. Foi isolada em
rag_clients.py para migração futura; evita trazer MLflow/Databricks Connect
como dependências transitivas de databricks-openai neste protótipo.

## Comportamento

Cada pergunta é independente, mesmo com histórico visual. Resposta, documentos,
seções e trechos ficam na sessão; feedback útil/não útil também. A exportação
JSON inclui esse conteúdo, duração, estado e ID, sem configuração de clientes.
Não existe persistência em Delta nem arquivo de feedback no servidor. Reiniciar
a sessão pode perder o histórico. O download grava somente quando solicitado
pelo usuário no navegador.

As fontes são documentos recuperados; a geração atual acrescenta todos os pares
recuperados como citações. Isso não prova suporte de cada afirmação. Exibimos
texto simples, sem HTML ou imagens externas fornecidas pelo modelo.
Erros de serviços recebem mensagem genérica e ID, sem detalhes de exceções que
possam conter credenciais. Não há diagnóstico técnico detalhado persistido nesta
versão. Um erro não é classificado como ausência de documentação.

## Databricks App (empacotamento da release)

A aplicação publicada e seus recursos estão descritos em
[`rag_app_producao.md`](rag_app_producao.md). Esta seção cobre só o
empacotamento local da release, que não utiliza CLI/API Databricks:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B apps/rag_chat/prepare_release.py
```

O destino padrão é `build/rag_chat_app` (ignorado pelo Git). O empacotador recusa
um destino existente, mesmo vazio: para uma nova release escolha outro caminho
com `--output build/rag_chat_app-v2`. Não há remoção ou sobrescrita automática.
Use caminhos sem symlinks nos diretórios pais.

A allowlist em `prepare_release.py` copia 12 arquivos: `app.yaml` e
`requirements.txt` na raiz, `apps/rag_chat/app.py` e nove módulos de
`src/analytics_ai`. Não há cópia recursiva do repositório. Arquivos ausentes e
symlinks são rejeitados antes de criar o destino. Uma falha de disco durante a
escrita pode deixar um artefato parcial, que não deve ser publicado.

`release.json` contém caminho de origem/destino, tamanho e SHA-256 de cada
arquivo, SHA-256 agregado do payload, commit Git e indicador de árvore suja.
Os hashes representam os bytes atuais, inclusive arquivos não commitados; o
SHA do commit sozinho não identifica esta release. O manifesto não inclui seu
próprio hash. Mesmo conteúdo produz o mesmo hash agregado, sem timestamp.
A allowlist evita incluir arquivos locais alheios à App, mas não substitui
revisão de segredos eventualmente inseridos nos próprios arquivos permitidos.

O artefato tem a estrutura necessária para os imports atuais. Não publique
somente apps/rag_chat nem a raiz completa do repositório. O descritor referencia
recursos por `valueFrom`, a serem vinculados apenas após aprovação:

| Chave do recurso | Recurso existente proposto | Permissão da App |
|---|---|---|
| `documentary-index` | `dev_lh_nautical.rag.document_chunks_index` | SELECT, USE CATALOG no catálogo e USE SCHEMA em rag |
| `generation-endpoint` | `databricks-meta-llama-3-3-70b-instruct` | CAN QUERY |

Nome proposto: `lh-nautical-rag-internal`, com acesso inicialmente restrito à
autora. Não existe arquivo de criação ou comando de deploy automático. O runtime
de Apps configura a porta do Streamlit. `app.yaml` inicia o processo em
`0.0.0.0`; a execução local recomendada permanece em `127.0.0.1`.
Não enviar perfil CLI ou credenciais ao artefato: a futura App usará sua própria
Service Principal com OAuth no backend. Vínculos de recursos podem conceder
permissões automaticamente e também exigem confirmação prévia.

Referências: [execução da App](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/app-runtime),
[recurso de índice](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/vector-search).

A App precisa de identidade própria com acesso ao índice, permissões UC
necessárias e consulta aos endpoints de geração/embedding usados. Acesso à App
inicialmente restrito à autora. Configuração OAuth é fornecida pelo Databricks,
sem campos de token na tela. Criação, grants e publicação exigem revisão e
confirmação; não usar as permissões de ingestão para o consumidor.

Antes de conectar usuários: conferir corpus/índice, permissões e baseline de
qualidade. O health check ainda precisa ser publicado/validado conforme roadmap.
Esta versão não possui streaming, memória conversacional, controle global de
concorrência, avaliação online pelo juiz ou feedback persistente.

## Testes sem endpoints

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m unittest tests.test_rag_service
# No ambiente que contém Streamlit:
/tmp/lh-rag-app-venv/bin/python -m unittest tests.test_rag_app
```

Os testes usam clientes simulados; não validam permissões ou endpoints reais.

### Validação do empacotamento

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m unittest tests.test_rag_app_release
```

Testes verificam lista exata, hashes, exclusão de arquivos sensíveis adicionais,
recusa de arquivos ausentes/symlinks/destino existente e imports sem acesso ao
repositório ou site-packages. Com Streamlit instalado, também abrem a tela do
artefato em subprocesso isolado. Nenhum teste precisa de autenticação remota.
