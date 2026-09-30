CREATE TABLE marts.fct_customer_revenue AS
SELECT
  c.id             AS customer_id,
  UPPER(c.country) AS country,
  SUM(s.amount)    AS total_revenue,
  COUNT(*)         AS order_count
FROM staging.stg_orders AS s
JOIN raw.customers AS c ON s.customer_id = c.id
GROUP BY c.id, UPPER(c.country);
