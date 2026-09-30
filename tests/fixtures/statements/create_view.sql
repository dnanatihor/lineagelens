CREATE VIEW analytics.v_orders AS
SELECT id AS order_id, LOWER(status) AS status_name
FROM raw.orders;
