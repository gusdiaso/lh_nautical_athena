-- Verifica que todo CEP está no formato XXXXX-XXX (8 dígitos + hífen).
-- Falha quando postal_code não corresponde ao padrão, evitando endereços com CEP inválido.
select *
from {{ ref('int_addresses') }}
where postal_code is not null
  and not rlike(postal_code, '^\\d{5}-\\d{3}$')