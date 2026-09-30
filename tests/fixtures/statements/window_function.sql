CREATE TABLE analytics.ranked AS
SELECT
  id,
  amount,
  ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY created_at) AS rn
FROM raw.orders;
