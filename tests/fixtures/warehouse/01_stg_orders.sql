CREATE TABLE staging.stg_orders AS
SELECT
  o.id                            AS order_id,
  o.customer_id                   AS customer_id,
  CAST(o.amount AS DECIMAL(12,2)) AS amount,
  o.created_at                    AS ordered_at
FROM raw.orders AS o
WHERE o.status <> 'cancelled';
