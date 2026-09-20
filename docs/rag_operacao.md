# Operação do RAG documental

## Objetivo

Este documento define como operar o RAG documental depois que ele está no ar:
como verificar se o índice responde, como detectar deriva entre a tabela Delta
e o índice, quando os recursos ficam ativos e o que fazer quando algo falha.

A verificação é automatizada pelo job `rag_health_check`, e não por inspeção
manual de telas. O procedimento manual descrito na seção 34 de
[implementacao-rag-documental-databricks.md](implementacao-rag-documental-databricks.md)
continua válido como diagnóstico profundo, mas deixou de ser o caminho normal.

## Job `rag_health_check`

Declarado em [resources/rag/rag_health_check.yml](../resources/rag/rag_health_check.yml),
com entrypoint [run_rag_health_check.py](../src/analytics_ai/run_rag_health_check.py)
e lógica testável em [rag_operations.py](../src/analytics_ai/rag_operations.py).

O job não cria recursos, não grava chunks e não chama o endpoint LLM. Ele só
lê o estado do índice, conta linhas, faz uma pergunta documental e tenta
alcançar os schemas do Data Warehouse.

### Sinais coletados

| Sinal | Origem | Como é interpretado |
|---|---|---|
| Prontidão do índice | `index.describe()` | `status.ready` e `status.detailed_state` |
| Linhas indexadas | `index.describe()` | `status.indexed_row_count` |
| Linhas da tabela | `SELECT COUNT(*)` na tabela de chunks | comparada com as linhas indexadas |
| Deriva | diferença entre tabela e índice | `0` é o único valor aceitável |
| Latência e recall mínimo | uma pergunta documental via `retrieve_chunks` | mede também a liveness do endpoint |
| Isolamento do warehouse | `SHOW TABLES IN <schema>` | ver [rag_seguranca.md](rag_seguranca.md) |

A leitura do estado do índice é tolerante ao formato: quando o SDK muda a
forma da descrição, o campo correspondente fica `NULL` e o relatório declara
"unknown" em vez de inventar um valor. Falha de `describe()`, de retrieval ou
da contagem é registrada no relatório; o job não quebra antes de reportar.

### Veredito

| Veredito | Quando ocorre |
|---|---|
| `healthy` | todos os sinais verdes e isolamento comprovado |
| `degraded` | índice não pronto, deriva de linhas, probe sem chunks, probe recusado, erro de leitura ou isolamento inconclusivo |
| `violated` | a identidade do RAG conseguiu listar um schema do Data Warehouse |

`violated` domina qualquer outro sinal: um índice perfeito com isolamento
rompido continua sendo `violated`. O parâmetro `fail_on` define a severidade
que quebra o job — `violated` por padrão, `degraded` para uma verificação
rígida antes da entrega, `never` para coleta puramente informativa.

### Como executar

```bash
databricks bundle deploy -t dev
databricks bundle run rag_health_check -t dev
```

Verificação rígida antes de uma apresentação ou entrega:

```bash
databricks bundle run rag_health_check -t dev --params fail_on=degraded,run_label=pre-entrega
```

Os parâmetros de job também permitem substituir `index_name`, `endpoint_name`,
`chunks_table`, `report_table`, `probe_question`, `isolation_schemas` e
`max_results`. Schemas informados sem catálogo herdam o catálogo de
`chunks_table`; uma lista vazia desliga a verificação de isolamento e, por
isso, produz `degraded` com o motivo explícito.

### Histórico

Com `--report-table`, cada execução acrescenta uma linha em
`dev_lh_nautical.rag.rag_health_checks`. A tabela é append-only e usa evolução
de schema, como a tabela de avaliação: execuções antigas continuam legíveis e
recebem `NULL` nas colunas novas.

```sql
SELECT
  run_timestamp,
  run_label,
  status,
  index_ready,
  indexed_row_count,
  table_rows,
  row_count_drift,
  probe_latency_seconds,
  isolation_violations,
  reasons_json
FROM dev_lh_nautical.rag.rag_health_checks
ORDER BY run_timestamp DESC;
```

## Rotina recomendada

1. `rag_ingestion` sempre que a documentação aprovada mudar. O job sobrescreve
   os chunks e só termina depois que a sincronização do índice conclui.
2. `rag_health_check` imediatamente depois da ingestão, para confirmar
   prontidão e ausência de deriva.
3. `rag_evaluation` com a suíte `smoke` (10 casos) antes de qualquer
   demonstração; a suíte `full` (35 casos) antes de uma entrega.
4. `rag_health_check` com `fail_on=degraded` como último passo antes de
   apresentar.
5. `rag_demo` apenas para a demonstração ao vivo, com pergunta documental.

Deriva de linhas depois de uma ingestão bem-sucedida indica sincronização
incompleta: rode `rag_ingestion` novamente antes de investigar o índice, pois
ele já dispara `sync()` e aguarda `wait_until_ready(wait_for_updates=True)`.

## Ciclo de vida dos recursos e quota

O workspace do projeto tem quotas e não expõe billing tradicional. A ausência
de um painel de custos não significa ausência de limite, então o ciclo de vida
é explícito:

- Nenhum job RAG tem agendamento. Ingestão, avaliação, health check e demo são
  executados manualmente, em janelas de trabalho.
- O pipeline do índice é `TRIGGERED`, nunca `CONTINUOUS`. Não há sincronização
  contínua consumindo recurso entre janelas.
- O endpoint de Vector Search e o índice permanecem provisionados durante todo
  o período de avaliação e apresentação (entrega em 20/09 e apresentações entre
  21 e 25/09). Excluir e recriar o índice custa provisionamento e novo
  embedding de todos os chunks, o que é um risco maior que mantê-lo ocioso.
- A remoção dos recursos de serving só deve ser avaliada depois da
  apresentação final, e por operação suportada pela plataforma.
- A avaliação é o passo mais caro: a suíte `full` faz uma chamada de geração
  por caso e até 24 chamadas de juiz, com intervalo mínimo de 2 segundos entre
  requisições. Rode `smoke` durante o desenvolvimento e reserve `full` para
  marcos.

## Falhas e recuperação

| Sintoma | Interpretação | Ação |
|---|---|---|
| `index is not ready` com estado de provisionamento | atualização em andamento | aguardar; não recriar o índice |
| `row count drift` | sincronização incompleta | reexecutar `rag_ingestion` |
| `retrieval probe failed` | endpoint ou índice indisponível | consultar estado do endpoint e do pipeline antes de qualquer recriação |
| `retrieval probe returned no chunks` | índice vazio ou filtro `status=approved` sem correspondência | conferir a ingestão e o campo `status` dos chunks |
| `probe question was refused` | a pergunta do probe caiu no guardrail | corrigir o parâmetro `probe_question`, não o guardrail |
| `warehouse isolation is broken` | privilégio indevido na identidade | tratar como incidente de segurança: ver [rag_seguranca.md](rag_seguranca.md) |
| `isolation inconclusive` | erro que não é de permissão | reexecutar; se persistir, verificar conectividade antes de concluir qualquer coisa |

Regras que não mudam: nunca excluir um índice funcional antes de o substituto
estar pronto e validado; nunca recriar índice enquanto `ready=false`; corrigir
a causa antes de recriar qualquer recurso.

## Estado atual

| Item | Estado |
|---|---|
| Módulo de operação e classificação de veredito | IMPLEMENTADO LOCALMENTE, com testes offline |
| Job `rag_health_check` no bundle | VALIDADO ESTATICAMENTE (`databricks bundle validate` OK em dev e prod) |
| Execução remota do health check | PENDENTE |
| Decisão de ciclo de vida e quota | DEFINIDA neste documento |
| Monitoramento automático com alerta | FORA DE ESCOPO nesta fase; o histórico é consultado sob demanda |

O job existe e é reproduzível, mas ainda não foi executado no workspace. A
primeira execução remota é parte dos próximos passos da entrega.
