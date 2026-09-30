CREATE TABLE analytics.pairs AS
SELECT a.id AS left_id, b.id AS right_id
FROM raw.orders AS a
JOIN raw.orders AS b ON a.customer_id = b.customer_id;
