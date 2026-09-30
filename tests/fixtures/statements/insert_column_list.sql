INSERT INTO marts.summary (customer_id, total)
SELECT c.id, SUM(o.amount)
FROM raw.customers AS c
JOIN raw.orders AS o ON c.id = o.customer_id
GROUP BY c.id;
