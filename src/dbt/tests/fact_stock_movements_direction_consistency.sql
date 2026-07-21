select
    nk_stock_movement_id as stock_movement_id
    , movement_direction
    , is_inbound
    , is_outbound
from {{ ref('fact_stock_movements') }}
where
    (movement_direction = 'entrada' and (not is_inbound or is_outbound))
    or (movement_direction = 'saida' and (not is_outbound or is_inbound))
    or (movement_direction = 'nao_classificado' and (is_inbound or is_outbound))
