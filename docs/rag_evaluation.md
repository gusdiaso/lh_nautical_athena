# Avaliação da RAG documental

## Objetivo

O Golden Dataset registra perguntas realistas e expectativas verificáveis para medir a RAG documental sem transformar uma resposta de referência em comparação literal. A versão inicial possui 30 casos, todos na suíte `full`, dos quais 10 formam a suíte rápida `smoke`.

O corpus avaliado é sempre a allowlist `DEFAULT_ALLOWED_PATHS` de `src/analytics_ai/rag_documents.py`. Fontes fora dela não são aceitas pelo validador, ainda que existam no repositório.

## Estrutura de um caso

Cada linha de `evaluation/rag_golden_dataset.jsonl` é um objeto JSON independente:

- `id`: identificador estável no formato `rag_NNN`;
- `inputs.question`: pergunta enviada à RAG;
- `expectations.expected_behavior`: `answer`, `insufficient_context`, `refuse_warehouse_data` ou `refuse_adversarial`;
- `expectations.expected_facts`: fatos pequenos e obrigatórios para casos respondíveis;
- `expectations.expected_sources`: caminho e seção que sustentam a resposta;
- `expectations.allowed_source_alternatives`: fontes editoriais opcionais que também são relevantes, mas não substituem as fontes primárias no cálculo de recall;
- `expectations.forbidden_claims`: afirmações de risco que não podem ser inventadas;
- `metadata.category`: tipo principal do caso;
- `metadata.difficulty`: `medium` ou `hard`;
- `metadata.suite`: sempre inclui `full` e pode incluir `smoke`;
- `metadata.scope`: `single_document`, `multi_document`, `out_of_scope` ou `adversarial`;
- `metadata.rationale`: motivo de a pergunta representar uma necessidade real.

## Validação local

Validar os 30 casos e imprimir a cobertura completa:

```bash
PYTHONPATH=src python -m analytics_ai.rag_evaluation validate --suite full
```

Validar o mesmo dataset e imprimir somente a cobertura dos 10 casos rápidos:

```bash
PYTHONPATH=src python -m analytics_ai.rag_evaluation validate --suite smoke
```

Executar os testes offline:

```bash
python -m unittest tests.test_rag_documents tests.test_rag_evaluation -v
```

Esses comandos não acessam Databricks, Vector Search ou LLM.

## Como adicionar ou revisar uma pergunta

1. Confirme que a necessidade veio de uma situação técnica real e possui uma intenção principal.
2. Confirme que todos os fatos respondíveis aparecem nos documentos da allowlist.
3. Use exatamente o caminho relativo e o heading Markdown editorial que contém a evidência. O Golden Dataset descreve o comportamento correto desejado e não deve reproduzir erros de metadado do chunker.
4. Escreva fatos curtos, independentes e verificáveis; não use uma resposta inteira como expectativa.
5. Registre apenas riscos reais em `forbidden_claims`.
6. Inclua o caso em `full`; altere a seleção `smoke` somente mantendo exatamente 10 casos.
7. Rode o validador, os testes e revise o relatório de documentos não cobertos.

Quando um documento indexado mudar, os casos afetados devem ser revisados junto com ele. Mudanças de heading quebram deliberadamente a validação editorial; mudanças de conteúdo exigem revisão humana dos fatos esperados, mesmo que o teste estrutural continue passando.

O relatório `section_metadata_mismatch` compara essas fontes editoriais com os metadados produzidos pelo chunker. Um mismatch não invalida o dataset e permanece como diagnóstico de regressão. O chunker atual separa Markdown por headings antes de aplicar tamanho e sobreposição; assim, a sobreposição fica restrita à seção editorial. Headings sem corpo não geram chunks, mas permanecem no breadcrumb hierárquico dos filhos. Todo chunk factual recebe um prefixo `CONTEXTO: ...` com esse breadcrumb, já descontado do limite total de 800 caracteres. Índices ingeridos antes dessa correção precisam ser reingeridos para receber os novos chunks e metadados.

## Métricas e arquitetura do avaliador

`rag_evaluation.py` fornece contratos neutros de provedor para um runner futuro registrar:

- comportamento observado e esperado;
- resposta;
- fontes recuperadas e fontes esperadas presentes/ausentes;
- citações apresentadas;
- cobertura dos fatos;
- latência;
- resultado individual e resumo geral.

As dimensões são separadas:

| Dimensão | Sinal | Avaliação atual |
|---|---|---|
| Recuperação | presença das fontes esperadas | determinística por caminho e seção |
| Geração | correção e completude dos fatos | requer revisão humana ou LLM-as-a-judge |
| Recusa | comportamento observado igual ao esperado | determinística |
| Desempenho | latência por caso e média | determinística quando houver runner |

Correspondência lexical não prova que um fato foi corretamente afirmado, negado ou contextualizado. Por isso a base local marca a cobertura de fatos como `None` e o resultado de respostas como “requer revisão”, em vez de produzir uma precisão artificial. Um avaliador futuro pode preencher essa dimensão por revisão humana ou por LLM-as-a-judge com rubrica, versão de prompt e evidências auditáveis.

### Métricas determinísticas

As métricas usam o par exato `(source_path, section)` e preservam a ordem dos chunks retornados. `expected_sources` representa evidência primária necessária; `allowed_source_alternatives` representa evidência editorial correta que pode contar como relevante para precisão e citações, sem esconder a ausência da fonte primária no recall ou no MRR.

Para casos técnicos (`expected_behavior=answer`), com `E` como fontes esperadas, `A` como alternativas permitidas, `R_k` como os primeiros `k` chunks recuperados e `C` como citações:

- `recall_at_k = |E ∩ R_k| / |E|`, considerando pares únicos encontrados;
- `precision_at_k = posições de R_k cujo par pertence a E ∪ A / k`; chunks repetidos ocupam posições distintas;
- `reciprocal_rank = 1 / rank` da primeira posição pertencente a `E`, ou `0` quando nenhuma aparece;
- `MRR` é a média de `reciprocal_rank` dos casos técnicos da execução;
- `citation_retrieved_rate = citações presentes em R_k / |C|`;
- `citation_allowed_rate = citações pertencentes a E ∪ A / |C|`;
- `technical_has_valid_citation` vale `1` quando existe citação simultaneamente real no corpus, recuperada e permitida; caso contrário, `0`;
- `technical_citation_coverage` é a média desse indicador nos casos técnicos.

Quando uma resposta técnica não contém citações, as duas taxas de citação são `0`. Para `insufficient_context`, `refuse_warehouse_data` e `refuse_adversarial`, todas essas métricas são `NULL`, pois não se aplicam.

Os diagnósticos são persistidos separadamente:

- `nonexistent_citations_json`: pares que não existem no corpus sanitizado;
- `not_retrieved_citations_json`: pares reais citados, mas ausentes dos chunks recuperados;
- `outside_allowed_citations_json`: pares citados fora de `E ∪ A`.

Cada execução grava linhas `record_type=case` e uma linha `record_type=run_summary`. Na linha agregada, as colunas das métricas contêm médias macro dos casos técnicos da mesma suíte e `case_id` permanece `NULL`. O writer usa evolução de schema Delta; linhas históricas permanecem legíveis e recebem `NULL` nas colunas novas.

Exemplo de consulta:

```sql
SELECT
  run_id,
  suite,
  recall_at_k AS mean_recall_at_k,
  precision_at_k AS mean_precision_at_k,
  reciprocal_rank AS mrr,
  citation_retrieved_rate,
  citation_allowed_rate,
  technical_has_valid_citation AS technical_citation_coverage
FROM dev_lh_nautical.rag.rag_evaluation_results
WHERE record_type = 'run_summary'
ORDER BY run_timestamp DESC;
```

As mesmas linhas agregadas armazenam `total_cases`, `passed_cases`, `failed_cases`, `needs_review_cases` e `deterministic_pass_rate`. Execuções gravadas antes desta evolução não são reprocessadas: suas colunas novas aparecem como `NULL`.

### Groundedness semântico com LLM-as-a-judge

A primeira versão reutiliza o endpoint configurado em `rag_llm_endpoint` (em dev, `databricks-meta-llama-3-3-70b-instruct`) como juiz, por meio do parâmetro `judge_endpoint`. Nenhum endpoint, recurso ou segredo adicional é criado. O juiz roda uma vez por resposta técnica não recusada e não altera a resposta da RAG.

A entrada contém exclusivamente pergunta, resposta, chunks sanitizados recuperados e citações extraídas:

```json
{
  "question": "...",
  "claims": [
    {"id": "claim_1", "text": "sentença literal extraída da resposta"}
  ],
  "evidence_candidates": [{"evidence_id": "evidence_1", "document": "docs/staging.md", "section": "Objetivo", "content": "..."}],
  "citations": [{"document": "docs/staging.md", "section": "Objetivo"}]
}
```

Saída estruturada proposta:

```json
{
  "claims": [
    {"claim_id": "claim_1", "verdict": "supported|unsupported|contradicted", "evidence_ids": ["evidence_1"]}
  ]
}
```

O código remove as linhas `Fonte:` e extrai deterministicamente sentenças materiais, preservando texto e ordem em IDs `claim_N`. Cada chunk recuperado recebe um ID determinístico por ordem de recuperação (`evidence_N`) e é enviado com documento, seção e conteúdo. O juiz não devolve nem reescreve texto ou Markdown: precisa julgar cada claim conhecida exatamente uma vez e selecionar somente IDs de evidência fornecidos. Uma sentença que misture fato sustentado e inferência sem base recebe `unsupported` integralmente. `supported` exige texto escrito ou claramente implicado pelos chunks; `unsupported` indica ausência de evidência textual; `contradicted` exige que o contexto afirme explicitamente o contrário. Evidências de `supported` e `contradicted` são obrigatórias. O código calcula `groundedness_score = supported / total de afirmações` e `grounded=true` somente quando todas são `supported`; esses dois valores não são responsabilidade do endpoint. O validador rejeita JSON incompleto, IDs ausentes/duplicados/desconhecidos ou evidência inventada. O JSON estruturado persistido inclui o catálogo completo `evidence_id → documento/seção/conteúdo` para auditoria. Respostas técnicas sem texto material depois da remoção das citações são `answer_not_produced` e não acionam o juiz.

O parser aceita uma única normalização conservadora para uma falha observada do endpoint: se `json.loads` falhar especificamente com `Extra data`, o primeiro objeto é extraído com `JSONDecoder.raw_decode` e aceito somente quando o sufixo restante, após espaços, é exatamente uma chave `}`. O conteúdo integral permanece em `judge_raw_output`, e `judge_structured_output_json.output_normalization` registra `removed_single_trailing_closing_brace`. Duas chaves, texto, Markdown ou outro objeto após o JSON continuam como `invalid_output`.

Por caso são persistidos status, versão do prompt, endpoint, latência, razão de falha, JSON bruto/estruturado, score, `grounded` e contagens por veredito. Os status são `completed`, `invalid_output`, `timeout` e `endpoint_error`; falhas jamais viram `grounded=true`. Recusas recebem `NULL`. A linha `run_summary` registra taxa e score médio de groundedness, totais por veredito e avaliações inválidas/indisponíveis. A evolução de schema mantém execuções históricas legíveis com `NULL` nas colunas novas.

O custo e a latência aumentam em uma chamada por caso técnico: até 8 no smoke e 24 no full. O custo monetário depende da tarifação do endpoint no workspace. Somente pergunta, resposta, citações e o `top_k` de chunks sanitizados são enviados — nunca fatos esperados, dados do warehouse ou credenciais. O juiz pode errar ao decompor afirmações ou interpretar implicações; antes de usá-lo como gate, deve ser calibrado contra amostra estratificada revisada por humanos, incluindo respostas sustentadas, incompletas, contraditórias e plausíveis sem suporte.

Geração e juiz compartilham o mesmo controle de chamadas. `request_interval_seconds` define o intervalo mínimo entre quaisquer duas requisições ao endpoint e vale `2` por padrão no job dev. Somente `RateLimitError`/HTTP 429 é repetido, no máximo três vezes após a tentativa inicial, com atrasos exponenciais aproximados de 2, 4 e 8 segundos mais jitter de até 250 ms. Erros de autenticação, demais 4xx, contrato ou saída inválida não são repetidos. Ao esgotar 429, a mensagem preserva o erro original e informa quatro tentativas totais; geração propaga `execution_error` e o juiz registra `endpoint_error`. No pior caso, o backoff acrescenta cerca de 14 segundos por chamada, além do intervalo, jitter e latência do endpoint.

### Dependência do terceiro PR

Esta evolução é intencionalmente dependente de `feature/rag-remote-evaluation`, que por sua vez depende de `feature/rag-golden-dataset`. Antes de abrir este terceiro PR contra `develop`, faça rebase após a integração sequencial dos dois PRs anteriores.

## Execução remota

O job `rag_evaluation` carrega o Golden Dataset uma vez e executa todos os casos selecionados no mesmo processo. O cliente de AI Search, o índice e o cliente do endpoint de geração também são reutilizados. Uma falha isolada é registrada como `failed` e não interrompe os demais casos.

Após o deploy do bundle, execute primeiro os 10 casos rápidos:

```bash
databricks bundle run rag_evaluation -t dev --params suite=smoke,run_label=pre-release
```

Para os 30 casos:

```bash
databricks bundle run rag_evaluation -t dev --params suite=full,run_label=release-candidate
```

Os parâmetros de job também permitem substituir `index_name`, `endpoint_name`, `report_table`, `question_endpoint`, `judge_endpoint`, `judge_timeout_seconds`, `request_interval_seconds`, `max_results` e `dataset`. O bundle passa obrigatoriamente `--dataset` usando `${workspace.file_path}/evaluation/rag_golden_dataset.jsonl`, isto é, o Golden Dataset sincronizado na raiz de arquivos da implantação. O entrypoint não depende de `__file__`; em execução local, informe um caminho explícito, por exemplo `--dataset evaluation/rag_golden_dataset.jsonl`.

A configuração dev grava, por padrão, em `dev_lh_nautical.rag.rag_evaluation_results`. A tabela é append-only: cada execução recebe um UUID e nunca apaga resultados anteriores.

Cada linha contém:

- identificação da execução (`run_id`, `run_timestamp`, `run_label`);
- caso, suíte, pergunta e comportamento esperado/observado;
- resposta, fontes recuperadas, citações e fontes esperadas em JSON;
- latência, status e listas JSON de motivos de falha ou revisão.

Os status significam:

- `passed`: uma recusa especial produziu exatamente a resposta segura esperada e não contém afirmação proibida;
- `failed`: houve erro de execução, ausência de resposta/fonte/citação válida, divergência determinística de recusa ou afirmação `unsupported`/`contradicted` validada pelo juiz;
- `needs_review`: a infraestrutura produziu resposta técnica sustentada pelo juiz, mas completude e calibração ainda exigem revisão humana; também cobre juiz inválido/indisponível e fonte editorial plausível diferente da expectativa.

A taxa de aprovação determinística usa apenas casos decididos (`passed / (passed + failed)`), excluindo `needs_review` do denominador. Correspondência literal só é usada para respostas canônicas de segurança e contexto insuficiente. Groundedness mede sustentação no contexto, não completude em relação aos fatos esperados nem correção absoluta; uma resposta técnica totalmente sustentada continua `needs_review` durante a calibração.

O resumo final apresenta totais, taxa determinística, latência média e IDs em `failed` ou `needs_review`. A execução remota continua necessária para medir recall real do índice, comportamento do endpoint de geração e latência end-to-end.

## Evolução do dataset

O conjunto deve crescer com perguntas reais observadas em suporte, revisão de PRs, onboarding e incidentes. Antes de incorporar uma pergunta, remova dados sensíveis, preserve sua intenção original, confirme a evidência documental e evite aumentar apenas a quantidade sem acrescentar cobertura. Casos obsoletos devem ser atualizados ou aposentados quando a arquitetura e a documentação versionada mudarem.
