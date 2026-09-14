# Changelog: operação, segurança e citações verificáveis do RAG

## Contexto

Este documento registra o que foi implementado na branch
`feature/rag-operacao-seguranca`, aberta a partir da `develop` já contendo o
MVP do RAG documental (PR #34) e os três PRs subsequentes da Fernanda: Golden
Dataset (#35), avaliação remota (#37) e métricas determinísticas com
groundedness (#38).

O objetivo foi fechar as pendências que ainda restavam depois desses quatro
PRs, listadas na seção 35 (antiga) de
[implementacao-rag-documental-databricks.md](implementacao-rag-documental-databricks.md):
monitoramento automatizado do índice, ACL de menor privilégio com isolamento
comprovado do Data Warehouse, e consolidação do entrypoint de geração com
validação de citações. Nenhuma mudança tocou o pipeline Bronze, Silver ou
Gold, nem alterou o comportamento dos módulos entregues nos PRs anteriores —
tudo foi construído por cima.

Este changelog é o registro técnico completo. Para uma versão resumida em
bullets, ver a mensagem enviada no Slack pelo Danilo.

## 1. Operação e saúde do índice

**Problema que resolvia:** o job de ingestão tinha `wait_for_index`, mas não
havia nenhuma forma automatizada de verificar, depois do fato, se o índice
estava saudável, se havia deriva entre a tabela e o índice, ou se a
identidade do RAG realmente estava isolada do warehouse. O procedimento
descrito na seção 34 do doc de arquitetura era só texto — dependia de alguém
rodar comandos manuais do `databricks` CLI e interpretar a saída.

**O que foi criado:**

- `src/analytics_ai/rag_operations.py` — módulo novo com toda a lógica de
  diagnóstico, testável sem workspace porque todo cliente Databricks é
  injetado:
  - `describe_index_state`: lê `index.describe()` e extrai prontidão, estado
    detalhado, linhas indexadas, tabela fonte e tipo de pipeline. A leitura é
    tolerante ao formato: se o SDK devolver uma estrutura diferente da
    esperada, o campo correspondente fica `None` e o relatório mostra
    "unknown" em vez de um valor inventado ou de uma exceção não tratada.
  - `count_table_rows`: conta linhas da tabela Delta de chunks via
    `SELECT COUNT(*)`, com o mesmo `validate_table_name` já usado no resto do
    projeto para impedir interpolação de identificador arbitrário em SQL.
  - `RowCountDrift`: compara linhas da tabela com linhas indexadas; deriva
    diferente de zero é sinal de sincronização incompleta.
  - `probe_retrieval`: faz uma pergunta documental real contra o índice
    (`retrieve_chunks`, já existente), mede a latência com um `clock`
    injetável (testável sem `time.sleep` real) e retorna os chunks e fontes
    recuperados. Isso também serve como teste de vida do endpoint de
    embedding e do endpoint LLM indiretamente, já que a busca híbrida os
    exercita.
  - `probe_warehouse_isolation` e `build_health_report`: descritos em
    detalhe na seção 2 abaixo, porque são compartilhados entre operação e
    segurança.
  - `HealthReport` / `health_report_row`: agregam os sinais num veredito
    único (`healthy`, `degraded`, `violated`) com lista de motivos, e achatam
    o relatório para uma linha de tabela Delta.
  - `append_health_report`: grava a linha em modo `append` com
    `mergeSchema=true`, no mesmo padrão de evolução de schema já usado pela
    tabela de avaliação — execuções antigas continuam legíveis.

- `src/analytics_ai/run_rag_health_check.py` — entrypoint do job, com os
  mesmos padrões dos outros `run_rag_*.py`: suporta execução como pacote ou
  como script solto, lê token/host do ambiente Databricks, valida os
  parâmetros antes de qualquer chamada remota.

- `resources/rag/rag_health_check.yml` — job novo no bundle, com parâmetros
  para índice, endpoint, tabela de chunks, tabela de relatório, pergunta de
  probe, schemas de isolamento e severidade de falha (`fail_on`).

- `docs/rag_operacao.md` — runbook completo: o que cada sinal significa, como
  interpretar o veredito, rotina recomendada de execução dos quatro jobs RAG,
  decisão explícita de ciclo de vida dos recursos no Free Edition (nenhum job
  agendado, pipeline sempre `TRIGGERED`, índice e endpoint ficam
  provisionados até depois da apresentação), e uma tabela de sintomas → ação
  para quando algo falha.

**Como o veredito é calculado:** `violated` domina qualquer outro sinal — um
índice perfeitamente saudável com isolamento rompido continua `violated`.
`degraded` cobre índice não pronto, deriva de linhas, probe sem chunks, probe
recusado pelo guardrail, falha ao ler o estado do índice, ou isolamento
inconclusivo/não testado. Só quando todos os sinais estão limpos e o
isolamento foi comprovado o veredito é `healthy`.

## 2. Segurança — ACL de menor privilégio

**Problema que resolvia:** não existia nenhum arquivo de `GRANT`, `DENY` ou
política de acesso para a identidade do RAG em todo o repositório. A seção 5
do documento de arquitetura listava isso como pendência desde a primeira
versão, e nenhum dos três PRs da Fernanda tratava desse ponto — o foco deles
foi avaliação, corretamente.

**O que foi criado:**

- `resources/security/rag_least_privilege.sql` — política comentada, no
  mesmo estilo do `apply_column_masks.sql` que já existia para mascaramento
  de PII. Concede à identidade do RAG apenas:
  - `USE CATALOG` no catálogo do ambiente (não concede leitura, só permite
    atravessar);
  - `USE SCHEMA` e `CREATE TABLE` no schema `rag`;
  - `SELECT`/`MODIFY` na tabela de chunks, nas duas tabelas de relatório
    (avaliação e health check);
  - `READ VOLUME` no volume de documentos aprovados;
  - `SELECT` no índice Delta Sync.

  E remove qualquer acesso aos schemas do warehouse com `REVOKE ALL
  PRIVILEGES`, seguido de `DENY` explícito em `bronze`, `silver` e `gold`
  como defesa em profundidade — `DENY` prevalece mesmo se um `GRANT` futuro
  vazar por herança de grupo, mas a ausência de `GRANT` continua sendo o
  controle primário.

- `resources/security/apply_rag_grants.py` — torna a política acima
  repetível e auditável, em vez de um script SQL solto que alguém copia e
  cola manualmente:
  - `--action verify | apply | revoke`, com `--dry-run` para revisar os
    statements exatos antes de executar qualquer coisa contra o workspace;
  - valida o nome do principal contra um alfabeto restrito
    (`[A-Za-z0-9._@-]+`) antes de interpolá-lo em qualquer statement SQL —
    evita injeção via nome de Service Principal;
  - reaproveita a mesma variável de ambiente (`DBT_HTTP_PATH`,
    `DBT_DATABRICKS_TOKEN[_PROD]`) e o mesmo conector
    `databricks-sql-connector` já usados por `apply_column_masks.py`.

- **Isolamento comprovado, não apenas declarado.** Esta é a parte mais
  importante da entrega: uma política de `GRANT`/`DENY` escrita em um arquivo
  não prova nada sozinha — Unity Catalog tem herança de privilégios (um
  `GRANT` no catálogo anula qualquer restrição no schema abaixo dele), então
  a única forma confiável de saber se o isolamento vale é testar
  empiricamente, com a própria identidade do RAG.

  `probe_warehouse_isolation` (em `rag_operations.py`) executa
  `SHOW TABLES IN <schema>` para cada schema do warehouse. Esse statement foi
  escolhido deliberadamente: ele exige o privilégio `USE SCHEMA`, que é o que
  governa todo `SELECT` abaixo dele, e **nunca retorna uma linha de dado
  operacional** — o probe não lê Bronze/Silver/Gold em nenhum cenário, nem
  mesmo quando o isolamento falha.

  A classificação do resultado tem três estados, não dois:

  | Resultado do statement | Interpretação |
  |---|---|
  | erro de permissão (`PERMISSION_DENIED`, `403`, `not authorized`, etc.) | isolamento comprovado |
  | sucesso | isolamento rompido — `violated` |
  | qualquer outro erro (timeout, conexão) | **inconclusivo**, nunca contado como isolamento OK |

  A terceira linha foi a decisão de design mais deliberada do módulo: numa
  implementação ingênua, qualquer exceção vira "bloqueado" e o sistema reporta
  isolamento saudável mesmo quando o teste não provou nada — um falso
  negativo de segurança silencioso. Aqui, erro que não é de permissão vira
  `degraded`, forçando alguém a olhar antes de confiar no resultado.

- `docs/rag_seguranca.md` — a política completa, a tabela de privilégios
  concedidos vs. negados, o procedimento de aplicação em 4 passos
  (verify → dry-run → apply → verify), e a explicação de por que a
  verificação empírica existe e como ela é lida.

## 3. Geração consolidada e citações verificáveis

**Problema que resolvia:** a seção 24 do doc de arquitetura registrava como
pendência a consolidação do entrypoint de demonstração com o contrato
`RagAnswer` que já existia em `rag_generation.py`. Na prática,
`run_rag_demo.py` remontava prompt e contexto manualmente, sem passar pelo
adaptador de geração nem pelo `RateLimitedChatClient` que a Fernanda criou
para pacing e retry de rate limit — ou seja, a demo não se beneficiava das
proteções que já existiam em outras partes do código.

**O que foi mudado:**

- `run_rag_demo.py` foi reescrito para usar `retrieve_chunks` (em vez de
  `retrieve_context`, que devolve só uma string), `RateLimitedChatClient` e
  `generate_answer`, na mesma composição já usada por
  `run_rag_evaluation.py`. Isso elimina uma segunda implementação divergente
  do mesmo fluxo.

- `check_citations` (novo, em `rag_generation.py`) — confere cada citação
  `Fonte: <documento> - Seção: <seção>` da resposta contra os pares
  `(source_path, section)` dos chunks efetivamente recuperados. Retorna um
  `CitationCheck` com as citações não encontradas no contexto. É uma
  verificação **determinística e local**: prova que a fonte citada estava no
  material enviado ao modelo, não que a afirmação em si está correta — essa
  segunda garantia continua sendo trabalho do groundedness por
  LLM-as-a-judge que já existe em `rag_groundedness.py`.

- O regex de citação (`Fonte: ... - Seção: ...`) estava duplicado, quase
  idêntico, em `rag_generation.py` e `rag_evaluation.py`. Agora existe uma
  única função (`parse_citation_pairs`), e `rag_evaluation.parse_citations`
  delega para ela — mantendo o tipo `ExpectedSource` que o resto da avaliação
  já espera, sem duplicar a lógica de parsing.

- A demo agora imprime, além da resposta, um bloco JSON com fontes, citações,
  se as citações são válidas, e quais não foram encontradas no contexto — e
  emite um aviso explícito quando uma resposta técnica não tem nenhuma
  citação auditável.

## 4. Documentação corrigida

**Problema que resolvia:** `docs/implementacao-rag-documental-databricks.md`
ainda descrevia o estado anterior aos PRs #35/#37/#38 — a matriz de estado
(seção 8) e a lista de pendências (seção 35) diziam "Golden Dataset:
PENDENTE" e "avaliação formal: PENDENTE" mesmo com essas duas coisas já
implementadas e testadas no repositório. Isso é um risco direto para o
critério de avaliação do checkpoint que exige documentação tecnicamente
correta e detalhada — um avaliador lendo só esse arquivo teria uma imagem
desatualizada do projeto.

**O que foi mudado:**

- Resumo executivo, escopo, matriz de estado (seção 8), estrutura de módulos
  (seção 9.1), seção de citações (24), seção de bundle (27), tabela de testes
  (28), seção de operação do índice (34), pendências (35) e próximos passos
  (36) foram todos revisados linha a linha para refletir o estado real do
  repositório na data desta entrega.
- Nova seção 39 ("Evolução da entrega") com uma tabela resumindo as cinco
  etapas da construção do RAG até aqui: MVP, Golden Dataset/ingestão,
  avaliação remota, métricas/groundedness, e esta entrega de
  operação/segurança.
- `docs/rag_mvp.md` ganhou entradas para os itens 8 e 9 da lista de próxima
  integração (verificação operacional e ACL), e o item 7 (Golden Dataset)
  deixou de dizer "Pendente" para "Implementado" com a execução remota das
  suítes marcada como o que falta.
- `README.md` não tinha nenhuma menção ao RAG — nem na tabela de status do
  projeto, nem na navegação, nem na estrutura de pastas. Adicionei uma seção
  "RAG Documental" com os quatro jobs, os comandos de cada um e os comandos
  de validação local, além de atualizar a tabela de status (RAG passou de
  "Gen AI: Futuro" para "Implementado"), a árvore de diretórios e a tabela de
  documentos.

## Arquivos

**Novos:**

| Arquivo | Conteúdo |
|---|---|
| `src/analytics_ai/rag_operations.py` | diagnóstico de saúde do índice e prova de isolamento |
| `src/analytics_ai/run_rag_health_check.py` | entrypoint do job `rag_health_check` |
| `resources/rag/rag_health_check.yml` | declaração do job no bundle |
| `resources/security/rag_least_privilege.sql` | política de menor privilégio comentada |
| `resources/security/apply_rag_grants.py` | script repetível para aplicar/verificar a política |
| `tests/test_rag_operations.py` | 31 testes offline do módulo de operação e das citações |
| `docs/rag_operacao.md` | runbook operacional |
| `docs/rag_seguranca.md` | política de segurança e isolamento |
| `docs/rag_operacao_seguranca_changelog.md` | este documento |

**Modificados:**

| Arquivo | Natureza da mudança |
|---|---|
| `src/analytics_ai/rag_databricks.py` | nova função `validate_schema_name` (reuso do padrão de `validate_table_name`) |
| `src/analytics_ai/rag_generation.py` | `CitationCheck`, `check_citations`, `parse_citation_pairs` |
| `src/analytics_ai/rag_evaluation.py` | `parse_citations` delega para `rag_generation`, regex duplicado removido |
| `src/analytics_ai/run_rag_demo.py` | reescrito sobre `RagAnswer` + citações verificadas |
| `resources/rag/rag_demo.yml` | variáveis do target `prod`, que estavam faltando |
| `docs/implementacao-rag-documental-databricks.md` | matriz de estado, pendências e seção de evolução atualizadas |
| `docs/rag_mvp.md` | itens de operação/ACL e status do Golden Dataset atualizados |
| `README.md` | seção RAG Documental, status do projeto, estrutura de pastas, tabela de documentos |

## Validação executada

- `python -m unittest tests.test_rag_documents tests.test_rag_endpoint tests.test_rag_evaluation tests.test_rag_groundedness tests.test_rag_operations` → **127 testes, todos passando** (31 novos, nenhum teste existente quebrado pela refatoração das citações).
- `python -m compileall -q src/analytics_ai resources/security tests` → sem erro.
- `PYTHONPATH=src python -m analytics_ai.rag_evaluation validate --suite full` → 30 casos válidos, 0 mismatch de seção.
- `PYTHONPATH=src python -m analytics_ai.rag_evaluation validate --suite smoke` → 10 casos válidos.
- `databricks bundle validate -t dev` → `Validation OK`.
- `databricks bundle validate -t prod` → `Validation OK` (1 recomendação não bloqueante sobre `root_path`, pré-existente e fora do escopo desta entrega).
- `run_rag_demo.py --help` e `run_rag_health_check.py --help` → confirma que ambos os entrypoints funcionam como script solto, não só como pacote.
- `apply_rag_grants.py --action apply --dry-run` → imprime os 17 statements exatos sem tocar o workspace; teste de principal inválido confirma que a validação de alfabeto bloqueia entrada maliciosa.

Nenhum teste remoto foi executado — nenhum job rodou no workspace, nenhum
recurso foi criado ou modificado no Databricks.

## O que fica pendente

Esta entrega é construção e validação local. O que falta é execução no
workspace, e depende de decisões que não são só técnicas (criar uma Service
Principal é uma decisão de quem administra o workspace):

1. Criar a Service Principal dedicada ao RAG.
2. Rodar `apply_rag_grants.py --action apply` com essa identidade.
3. Rodar `rag_health_check` e confirmar o primeiro veredito real — hoje,
   rodando com a identidade de quem faz o deploy (que tem acesso ao
   warehouse), o veredito esperado é `violated`, e isso é o comportamento
   correto do sistema, não um bug.
4. Rodar a suíte `smoke` da avaliação, revisar falhas, depois rodar `full` e
   registrar os números reais nos documentos (`rag_evaluation.md` e a matriz
   de estado do doc de arquitetura).
5. Calibrar o juiz de groundedness contra uma amostra revisada por humanos
   antes de tratá-lo como critério de aprovação — ele ainda não foi calibrado.

## Referências

- [docs/rag_operacao.md](rag_operacao.md)
- [docs/rag_seguranca.md](rag_seguranca.md)
- [docs/implementacao-rag-documental-databricks.md](implementacao-rag-documental-databricks.md)
- [docs/rag_mvp.md](rag_mvp.md)
- [docs/rag_evaluation.md](rag_evaluation.md)
- Branch: `feature/rag-operacao-seguranca` (pushada, sem PR aberto)
