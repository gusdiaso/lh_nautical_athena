# Segurança e isolamento do RAG documental

## O que está sendo protegido

O RAG responde sobre documentação versionada. O risco que importa não é uma
resposta errada: é o sistema virar um caminho indireto para dados operacionais
ou para segredos. Duas garantias precisam valer ao mesmo tempo:

1. o corpus não contém segredo nem dado operacional;
2. a identidade que executa o RAG não consegue ler o Data Warehouse, mesmo que
   o modelo seja induzido a tentar.

A primeira garantia é de código. A segunda é de Unity Catalog, e é a mais
forte das duas: um prompt não contorna a ausência de privilégio.

## Camadas de defesa

| Camada | Onde vive | O que garante | Limite |
|---|---|---|---|
| Allowlist explícita | `DEFAULT_ALLOWED_PATHS` em [rag_documents.py](../src/analytics_ai/rag_documents.py) | só entra no corpus arquivo aprovado | precisa de revisão humana ao crescer |
| Sanitização | `sanitize_text` | mascara tokens, senhas, chaves e e-mails | é barreira por padrão, não anonimização provada |
| Guardrail pré-retrieval | `guard_question` em [rag_prompt.py](../src/analytics_ai/rag_prompt.py) | bloqueia pergunta operacional antes do índice e do LLM | regex tem falso positivo e falso negativo |
| Contexto delimitado | `format_context` e prompt de sistema | trata documento como dado, não como instrução | não elimina prompt injection |
| Citação verificável | `check_citations` em [rag_generation.py](../src/analytics_ai/rag_generation.py) | detecta citação que não veio do contexto recuperado | não prova que a afirmação está correta |
| Menor privilégio | Unity Catalog | impede acesso técnico ao warehouse | precisa ser aplicado e verificado |

As cinco primeiras camadas reduzem probabilidade. A última remove capacidade,
e por isso é a que não pode ficar pendente.

## Política de menor privilégio

A identidade do RAG deve ser uma Service Principal dedicada, usada apenas
pelos jobs `rag_ingestion`, `rag_evaluation`, `rag_health_check` e `rag_demo`.

O que a identidade recebe:

| Recurso | Privilégio | Motivo |
|---|---|---|
| Catálogo do ambiente | `USE CATALOG` | atravessar o catálogo; não concede leitura |
| Schema `rag` | `USE SCHEMA`, `CREATE TABLE` | criar e usar objetos documentais |
| `rag.document_chunks` | `SELECT`, `MODIFY` | a ingestão sobrescreve os chunks |
| `rag.documents` (Volume) | `READ VOLUME` | ler os documentos aprovados |
| `rag.document_chunks_index` | `SELECT` | executar busca híbrida |
| `rag.rag_evaluation_results` e `rag.rag_health_checks` | `SELECT`, `MODIFY` | relatórios append-only |

O que a identidade não recebe, em nenhuma hipótese:

- `USE SCHEMA` em `bronze`, `silver` ou `gold`;
- `SELECT` em qualquer tabela dessas camadas;
- privilégio de leitura concedido no nível do catálogo, que é herdado por
  todos os schemas abaixo dele;
- participação em grupos amplos como `lh_nautical_dev`, cujos privilégios
  anulariam a política.

A armadilha real do Unity Catalog é a herança: privilégios descem do catálogo
para o schema e do schema para a tabela. Uma política correta no schema `rag`
não protege nada se a mesma identidade tiver `SELECT` no catálogo, ou se
pertencer a um grupo que tenha. Por isso a verificação não pode ser só ler o
arquivo de grants — precisa ser empírica.

## Como aplicar

A política comentada está em
[rag_least_privilege.sql](../resources/security/rag_least_privilege.sql) e é
aplicável de forma repetível por
[apply_rag_grants.py](../resources/security/apply_rag_grants.py), no mesmo
padrão já usado pelo mascaramento de colunas.

```bash
# 1. Inspecionar o que a identidade tem hoje
python resources/security/apply_rag_grants.py --principal <application-id> --action verify

# 2. Revisar os statements antes de executar qualquer coisa
python resources/security/apply_rag_grants.py --principal <application-id> --action apply --dry-run

# 3. Aplicar com uma identidade OWNER do catálogo
python resources/security/apply_rag_grants.py --principal <application-id> --action apply

# 4. Confirmar o resultado
python resources/security/apply_rag_grants.py --principal <application-id> --action verify
```

`--action apply` concede o acesso documental mínimo, remove privilégios
indevidos nos schemas do warehouse com `REVOKE` e acrescenta `DENY` como
defesa em profundidade. `DENY` prevalece sobre um `GRANT` herdado que apareça
depois, mas a ausência de `GRANT` continua sendo o controle primário.

O nome do principal é validado antes de entrar no SQL: só letras, dígitos e
`. _ - @`. Isso evita interpolar um identificador arbitrário em um statement
administrativo.

## Verificação empírica

Declarar a política aplicada não é evidência. A evidência é o job
`rag_health_check`, que executa `SHOW TABLES IN <schema>` para cada schema do
warehouse usando a própria identidade do RAG. `SHOW TABLES IN` exige
`USE SCHEMA`, que é o privilégio que governa todo `SELECT` abaixo dele, e não
lê nenhuma linha de dado operacional.

| Resultado do statement | Leitura | Veredito |
|---|---|---|
| erro de permissão | a identidade não alcança o schema | isolamento comprovado |
| sucesso | a identidade alcança o schema | `violated`: incidente de segurança |
| erro que não é de permissão | nada foi provado | `inconclusive`, tratado como `degraded` |

A terceira linha é deliberada: qualquer falha vira "isolamento OK" em uma
implementação ingênua, e foi exatamente esse falso negativo que se decidiu
evitar. O vocabulário de erro considerado permissão está em
`_PERMISSION_DENIED_PATTERN` em [rag_operations.py](../src/analytics_ai/rag_operations.py).

Se o veredito for `violated`, o tratamento é de incidente: identificar qual
`GRANT` ou grupo concedeu o acesso, remover, reexecutar o health check e só
então voltar a usar o RAG.

## Corpus e segredos

Nunca são indexados: `target/`, `dbt_packages/`, `.databricks/`, `logs/`,
`.env`, dados brutos e tabelas exportadas. Antes de publicar o corpus, qualquer
token exposto no ambiente local ou no histórico do Git deve ser revogado e
rotacionado — sanitização de texto não desfaz um segredo já vazado.

Os documentos de RAG (`rag_mvp.md`, `rag_evaluation.md`, `rag_operacao.md`,
este arquivo e o documento de implementação) estão fora da allowlist por
decisão explícita. Incluí-los é permitido pelo escopo do checkpoint, mas
exigiria reingestão e revisão dos casos do Golden Dataset afetados; a
expansão do corpus fica registrada como opção, não como pendência silenciosa.

## Estado atual

| Item | Estado |
|---|---|
| Política de menor privilégio versionada e parametrizável | IMPLEMENTADA |
| Verificação empírica de isolamento automatizada | IMPLEMENTADA LOCALMENTE, com testes offline |
| Service Principal dedicada criada no workspace | PENDENTE |
| `GRANT`/`DENY` aplicados e confirmados no workspace | PENDENTE |
| Nomes exatos de privilégio confirmados na versão do UC do workspace | PENDENTE, por isso o `--dry-run` existe |
| Rotação de credenciais da identidade | PENDENTE |

Enquanto a Service Principal dedicada não existir, os jobs rodam com a
identidade do usuário que fez o deploy, que tem acesso ao warehouse. Nessa
configuração o health check tende a reportar `violated`, e o relatório está
certo: o isolamento técnico ainda não existe.
