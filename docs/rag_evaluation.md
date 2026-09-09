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

Os parâmetros de job também permitem substituir `index_name`, `endpoint_name`, `report_table`, `question_endpoint`, `max_results` e `dataset`. O bundle passa obrigatoriamente `--dataset` usando `${workspace.file_path}/evaluation/rag_golden_dataset.jsonl`, isto é, o Golden Dataset sincronizado na raiz de arquivos da implantação. O entrypoint não depende de `__file__`; em execução local, informe um caminho explícito, por exemplo `--dataset evaluation/rag_golden_dataset.jsonl`.

A configuração dev grava, por padrão, em `dev_lh_nautical.rag.rag_evaluation_results`. A tabela é append-only: cada execução recebe um UUID e nunca apaga resultados anteriores.

Cada linha contém:

- identificação da execução (`run_id`, `run_timestamp`, `run_label`);
- caso, suíte, pergunta e comportamento esperado/observado;
- resposta, fontes recuperadas, citações e fontes esperadas em JSON;
- latência, status e listas JSON de motivos de falha ou revisão.

Os status significam:

- `passed`: uma recusa especial produziu exatamente a resposta segura esperada e não contém afirmação proibida;
- `failed`: houve erro de execução, ausência de resposta/fonte/citação válida ou divergência determinística de recusa;
- `needs_review`: a infraestrutura produziu uma resposta técnica com evidências, mas correção, completude e groundedness ainda exigem revisão humana. Uma fonte editorial plausível diferente da expectativa também recebe este status, não uma reprovação automática.

A taxa de aprovação determinística usa apenas casos decididos (`passed / (passed + failed)`), excluindo `needs_review` do denominador. Correspondência literal só é usada para as respostas canônicas de segurança e contexto insuficiente. Esta primeira versão não usa LLM-as-a-judge e não aprova respostas técnicas por palavras-chave.

O resumo final apresenta totais, taxa determinística, latência média e IDs em `failed` ou `needs_review`. A execução remota continua necessária para medir recall real do índice, comportamento do endpoint de geração e latência end-to-end.

## Evolução do dataset

O conjunto deve crescer com perguntas reais observadas em suporte, revisão de PRs, onboarding e incidentes. Antes de incorporar uma pergunta, remova dados sensíveis, preserve sua intenção original, confirme a evidência documental e evite aumentar apenas a quantidade sem acrescentar cobertura. Casos obsoletos devem ser atualizados ou aposentados quando a arquitetura e a documentação versionada mudarem.
