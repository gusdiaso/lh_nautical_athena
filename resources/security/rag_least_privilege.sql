-- =====================================================================
-- Menor privilegio da identidade do RAG documental — Unity Catalog
-- =====================================================================
-- Objetivo:  Garantir que a identidade que executa os jobs do RAG
--            alcance apenas os recursos documentais e nunca o Data
--            Warehouse (Bronze, Silver e Gold).
--
-- Recursos permitidos:
--   Volume  → dev_lh_nautical.rag.documents        (documentos aprovados)
--   Tabela  → dev_lh_nautical.rag.document_chunks  (chunks documentais)
--   Indice  → dev_lh_nautical.rag.document_chunks_index
--   Tabelas → rag_evaluation_results / rag_health_checks (append-only)
--
-- Recursos negados:
--   dev_lh_nautical.bronze / silver / gold e qualquer tabela dentro deles.
--
-- Como executar:
--   1. Conecte-se com uma identidade OWNER do catalogo (ou metastore admin).
--   2. Substitua <SERVICE_PRINCIPAL> pelo applicationId da Service Principal
--      dedicada ao RAG. Nao use um usuario nominal nem a SP do pipeline dbt.
--   3. Para producao, troque dev_lh_nautical por prod_lh_nautical.
--   4. Rode o job rag_health_check depois de aplicar: ele e a verificacao
--      empirica de que o isolamento realmente vale.
--
-- Pre-requisitos e cuidados:
--   - Privilegios em Unity Catalog sao herdados de cima para baixo. Um GRANT
--     de SELECT no CATALOGO anula todo este arquivo, portanto a SP do RAG nao
--     deve pertencer a grupos com privilegios amplos (por exemplo
--     lh_nautical_dev), e nenhum privilegio de leitura deve existir no nivel
--     de catalogo.
--   - DENY existe como defesa em profundidade; a ausencia de GRANT continua
--     sendo o controle primario.
--   - Os nomes exatos de privilegios variam com a versao do Unity Catalog do
--     workspace. Rode primeiro em modo verificacao e confirme cada statement
--     antes de declarar a politica aplicada.
-- =====================================================================

-- =====================================================================
-- 1. ACESSO DOCUMENTAL MINIMO
-- =====================================================================
-- USE CATALOG apenas permite atravessar o catalogo; nao concede leitura.

GRANT USE CATALOG ON CATALOG dev_lh_nautical TO `<SERVICE_PRINCIPAL>`;
GRANT USE SCHEMA ON SCHEMA dev_lh_nautical.rag TO `<SERVICE_PRINCIPAL>`;

-- A ingestao sobrescreve os chunks e pode precisar recriar a tabela e o indice.
GRANT CREATE TABLE ON SCHEMA dev_lh_nautical.rag TO `<SERVICE_PRINCIPAL>`;
GRANT SELECT, MODIFY ON TABLE dev_lh_nautical.rag.document_chunks TO `<SERVICE_PRINCIPAL>`;

-- Leitura dos documentos aprovados publicados no Volume.
GRANT READ VOLUME ON VOLUME dev_lh_nautical.rag.documents TO `<SERVICE_PRINCIPAL>`;

-- O indice Delta Sync e um securable proprio; a consulta hibrida exige SELECT.
GRANT SELECT ON TABLE dev_lh_nautical.rag.document_chunks_index TO `<SERVICE_PRINCIPAL>`;

-- Relatorios append-only de avaliacao e de saude operacional.
GRANT SELECT, MODIFY ON TABLE dev_lh_nautical.rag.rag_evaluation_results TO `<SERVICE_PRINCIPAL>`;
GRANT SELECT, MODIFY ON TABLE dev_lh_nautical.rag.rag_health_checks TO `<SERVICE_PRINCIPAL>`;

-- =====================================================================
-- 2. REMOCAO DE QUALQUER ACESSO AO DATA WAREHOUSE
-- =====================================================================
-- REVOKE remove privilegios concedidos anteriormente por engano.

REVOKE ALL PRIVILEGES ON SCHEMA dev_lh_nautical.bronze FROM `<SERVICE_PRINCIPAL>`;
REVOKE ALL PRIVILEGES ON SCHEMA dev_lh_nautical.silver FROM `<SERVICE_PRINCIPAL>`;
REVOKE ALL PRIVILEGES ON SCHEMA dev_lh_nautical.gold FROM `<SERVICE_PRINCIPAL>`;

-- =====================================================================
-- 3. DEFESA EM PROFUNDIDADE (DENY)
-- =====================================================================
-- DENY prevalece sobre qualquer GRANT herdado que apareca no futuro.

DENY USE SCHEMA ON SCHEMA dev_lh_nautical.bronze TO `<SERVICE_PRINCIPAL>`;
DENY USE SCHEMA ON SCHEMA dev_lh_nautical.silver TO `<SERVICE_PRINCIPAL>`;
DENY USE SCHEMA ON SCHEMA dev_lh_nautical.gold TO `<SERVICE_PRINCIPAL>`;

DENY SELECT ON SCHEMA dev_lh_nautical.bronze TO `<SERVICE_PRINCIPAL>`;
DENY SELECT ON SCHEMA dev_lh_nautical.silver TO `<SERVICE_PRINCIPAL>`;
DENY SELECT ON SCHEMA dev_lh_nautical.gold TO `<SERVICE_PRINCIPAL>`;

-- =====================================================================
-- 4. VERIFICACAO
-- =====================================================================
-- O resultado esperado e: privilegios documentais presentes no schema rag e
-- nenhum privilegio de leitura nos schemas do warehouse.

SHOW GRANTS `<SERVICE_PRINCIPAL>` ON CATALOG dev_lh_nautical;
SHOW GRANTS `<SERVICE_PRINCIPAL>` ON SCHEMA dev_lh_nautical.rag;
SHOW GRANTS `<SERVICE_PRINCIPAL>` ON SCHEMA dev_lh_nautical.bronze;
SHOW GRANTS `<SERVICE_PRINCIPAL>` ON SCHEMA dev_lh_nautical.silver;
SHOW GRANTS `<SERVICE_PRINCIPAL>` ON SCHEMA dev_lh_nautical.gold;
