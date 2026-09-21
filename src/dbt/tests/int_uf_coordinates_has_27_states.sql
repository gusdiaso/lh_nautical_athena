-- Garante as 27 unidades federativas na lista de UFs candidatas.
-- Falha se o seed ganhar duplicata de UF ou perder uma.
select count(*) as state_count
from {{ ref('int_uf_coordinates') }}
having count(*) <> 27
