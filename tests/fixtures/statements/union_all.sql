CREATE TABLE analytics.out AS
SELECT id, amount FROM raw.orders
UNION ALL
SELECT id, amount FROM raw.archive_orders;
