CREATE TABLE analytics.out AS
WITH base AS (
  SELECT id, amount FROM raw.orders
),
doubled AS (
  SELECT id, amount * 2 AS amount FROM base
)
SELECT id AS order_id, amount FROM doubled;
