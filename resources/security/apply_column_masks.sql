-- =====================================================================
-- Column Masking — Unity Catalog
-- =====================================================================
-- Objetivo:  Ocultar dados sensíveis de colunas específicas para
--            usuários que não pertencem ao grupo autorizado.
--
-- Camadas protegidas:
--   Bronze → bronze.customers / bronze.employees / bronze.suppliers
--   Silver → silver.int_customers / silver.int_employees / silver.int_suppliers
--   Gold   → gold.dim_customers / gold.dim_employees / gold.dim_suppliers
--
-- Como funciona:
--   O Databricks Unity Catalog aplica a máscara em query time:
--   quem pertence ao grupo lh_nautical_dev enxerga o valor real;
--   os demais veem o texto mascarado.
--
-- Como executar:
--   1. Conecte-se no Databricks com uma role que tenha permissão
--      (admin ou owner dos schemas gold/silver/bronze).
--   2. Execute este script no SQL Editor do Databricks ou via
--      Databricks CLI (databricks sql execute).
--
-- Pré-requisitos:
--   - Catálogo gerenciado pelo Unity Catalog
--   - Grupo lh_nautical_dev existente no workspace Databricks
--   - Tabelas de todas as camadas já materializadas
-- =====================================================================

-- =====================================================================
-- 1. FUNÇÕES DE MÁSCARA
-- =====================================================================
-- As funções precisam ser criadas em um schema que todos os usuários
-- consigam acessar (gold, já que é a camada de consumo).

CREATE OR REPLACE FUNCTION dev_lh_nautical.gold.mask_full(value STRING)
  RETURN CASE
    WHEN is_member('lh_nautical_dev') THEN value
    ELSE '***MASKED***'
  END;

CREATE OR REPLACE FUNCTION dev_lh_nautical.gold.mask_cpf(value STRING)
  RETURN CASE
    WHEN is_member('lh_nautical_dev') THEN value
    ELSE '***MASKED***'
  END;

CREATE OR REPLACE FUNCTION dev_lh_nautical.gold.mask_email(value STRING)
  RETURN CASE
    WHEN is_member('lh_nautical_dev') THEN value
    ELSE '***MASKED***'
  END;

CREATE OR REPLACE FUNCTION dev_lh_nautical.gold.mask_phone(value STRING)
  RETURN CASE
    WHEN is_member('lh_nautical_dev') THEN value
    ELSE '***MASKED***'
  END;

-- =====================================================================
-- 2. APLICAR MÁSCARAS — BRONZE
-- =====================================================================
-- Dados brutos do SQL Server.

-- bronze.customers
ALTER TABLE dev_lh_nautical.bronze.customers
  ALTER COLUMN tax_id SET MASK dev_lh_nautical.gold.mask_full;
ALTER TABLE dev_lh_nautical.bronze.customers
  ALTER COLUMN email SET MASK dev_lh_nautical.gold.mask_email;
ALTER TABLE dev_lh_nautical.bronze.customers
  ALTER COLUMN phone SET MASK dev_lh_nautical.gold.mask_phone;

-- bronze.employees
ALTER TABLE dev_lh_nautical.bronze.employees
  ALTER COLUMN cpf SET MASK dev_lh_nautical.gold.mask_cpf;
ALTER TABLE dev_lh_nautical.bronze.employees
  ALTER COLUMN email SET MASK dev_lh_nautical.gold.mask_email;

-- bronze.suppliers
ALTER TABLE dev_lh_nautical.bronze.suppliers
  ALTER COLUMN tax_id SET MASK dev_lh_nautical.gold.mask_full;
ALTER TABLE dev_lh_nautical.bronze.suppliers
  ALTER COLUMN email SET MASK dev_lh_nautical.gold.mask_email;
ALTER TABLE dev_lh_nautical.bronze.suppliers
  ALTER COLUMN phone SET MASK dev_lh_nautical.gold.mask_phone;

-- =====================================================================
-- 3. APLICAR MÁSCARAS — SILVER (Intermediate)
-- =====================================================================
-- Dados tratados, que alimentam as dimensões Gold.

-- silver.int_customers
ALTER TABLE dev_lh_nautical.silver.int_customers
  ALTER COLUMN tax_id SET MASK dev_lh_nautical.gold.mask_full;
ALTER TABLE dev_lh_nautical.silver.int_customers
  ALTER COLUMN email SET MASK dev_lh_nautical.gold.mask_email;
ALTER TABLE dev_lh_nautical.silver.int_customers
  ALTER COLUMN phone SET MASK dev_lh_nautical.gold.mask_phone;

-- silver.int_employees
ALTER TABLE dev_lh_nautical.silver.int_employees
  ALTER COLUMN cpf SET MASK dev_lh_nautical.gold.mask_cpf;
ALTER TABLE dev_lh_nautical.silver.int_employees
  ALTER COLUMN email SET MASK dev_lh_nautical.gold.mask_email;

-- silver.int_suppliers
ALTER TABLE dev_lh_nautical.silver.int_suppliers
  ALTER COLUMN tax_id SET MASK dev_lh_nautical.gold.mask_full;
ALTER TABLE dev_lh_nautical.silver.int_suppliers
  ALTER COLUMN email SET MASK dev_lh_nautical.gold.mask_email;
ALTER TABLE dev_lh_nautical.silver.int_suppliers
  ALTER COLUMN phone SET MASK dev_lh_nautical.gold.mask_phone;

-- =====================================================================
-- 4. APLICAR MÁSCARAS — GOLD (Marts)
-- =====================================================================
-- 4. APLICAR MÁSCARAS — GOLD (Marts)
-- =====================================================================
-- Modelo dimensional, consumido por BI e relatórios.

-- gold.dim_customers
ALTER TABLE dev_lh_nautical.gold.dim_customers
  ALTER COLUMN tax_id SET MASK dev_lh_nautical.gold.mask_full;
ALTER TABLE dev_lh_nautical.gold.dim_customers
  ALTER COLUMN email SET MASK dev_lh_nautical.gold.mask_email;
ALTER TABLE dev_lh_nautical.gold.dim_customers
  ALTER COLUMN phone SET MASK dev_lh_nautical.gold.mask_phone;

-- gold.dim_employees
ALTER TABLE dev_lh_nautical.gold.dim_employees
  ALTER COLUMN cpf SET MASK dev_lh_nautical.gold.mask_cpf;
ALTER TABLE dev_lh_nautical.gold.dim_employees
  ALTER COLUMN email SET MASK dev_lh_nautical.gold.mask_email;

-- gold.dim_suppliers
ALTER TABLE dev_lh_nautical.gold.dim_suppliers
  ALTER COLUMN tax_id SET MASK dev_lh_nautical.gold.mask_full;
ALTER TABLE dev_lh_nautical.gold.dim_suppliers
  ALTER COLUMN email SET MASK dev_lh_nautical.gold.mask_email;
ALTER TABLE dev_lh_nautical.gold.dim_suppliers
  ALTER COLUMN phone SET MASK dev_lh_nautical.gold.mask_phone;

-- =====================================================================
-- 5. (OPCIONAL) REMOVER MÁSCARAS
-- =====================================================================
-- Use apenas se precisar desfazer:
/*
-- Bronze
ALTER TABLE dev_lh_nautical.bronze.customers ALTER COLUMN tax_id DROP MASK;
ALTER TABLE dev_lh_nautical.bronze.customers ALTER COLUMN email DROP MASK;
ALTER TABLE dev_lh_nautical.bronze.customers ALTER COLUMN phone DROP MASK;
ALTER TABLE dev_lh_nautical.bronze.employees ALTER COLUMN cpf DROP MASK;
ALTER TABLE dev_lh_nautical.bronze.employees ALTER COLUMN email DROP MASK;
ALTER TABLE dev_lh_nautical.bronze.suppliers ALTER COLUMN tax_id DROP MASK;
ALTER TABLE dev_lh_nautical.bronze.suppliers ALTER COLUMN email DROP MASK;
ALTER TABLE dev_lh_nautical.bronze.suppliers ALTER COLUMN phone DROP MASK;

-- Silver
ALTER TABLE dev_lh_nautical.silver.int_customers ALTER COLUMN tax_id DROP MASK;
ALTER TABLE dev_lh_nautical.silver.int_customers ALTER COLUMN email DROP MASK;
ALTER TABLE dev_lh_nautical.silver.int_customers ALTER COLUMN phone DROP MASK;
ALTER TABLE dev_lh_nautical.silver.int_employees ALTER COLUMN cpf DROP MASK;
ALTER TABLE dev_lh_nautical.silver.int_employees ALTER COLUMN email DROP MASK;
ALTER TABLE dev_lh_nautical.silver.int_suppliers ALTER COLUMN tax_id DROP MASK;
ALTER TABLE dev_lh_nautical.silver.int_suppliers ALTER COLUMN email DROP MASK;
ALTER TABLE dev_lh_nautical.silver.int_suppliers ALTER COLUMN phone DROP MASK;

-- Gold
ALTER TABLE dev_lh_nautical.gold.dim_customers ALTER COLUMN tax_id DROP MASK;
ALTER TABLE dev_lh_nautical.gold.dim_customers ALTER COLUMN email DROP MASK;
ALTER TABLE dev_lh_nautical.gold.dim_customers ALTER COLUMN phone DROP MASK;
ALTER TABLE dev_lh_nautical.gold.dim_employees ALTER COLUMN cpf DROP MASK;
ALTER TABLE dev_lh_nautical.gold.dim_employees ALTER COLUMN email DROP MASK;
ALTER TABLE dev_lh_nautical.gold.dim_suppliers ALTER COLUMN tax_id DROP MASK;
ALTER TABLE dev_lh_nautical.gold.dim_suppliers ALTER COLUMN email DROP MASK;
ALTER TABLE dev_lh_nautical.gold.dim_suppliers ALTER COLUMN phone DROP MASK;
*/
