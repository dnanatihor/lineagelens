CREATE TABLE analytics.out AS
SELECT sub.id AS order_id
FROM (
  SELECT id FROM raw.orders
) AS sub;
