-- Verifica que a quantidade recebida em recebimentos de mercadoria é positiva.
-- Falha quando quantity_received é zero ou negativo, evitando registros de recebimento sem mercadoria.
select
    goods_receipt_item_id
    , goods_receipt_id
    , quantity_received
from {{ ref('int_goods_receipt_items') }}
where quantity_received <= 0
