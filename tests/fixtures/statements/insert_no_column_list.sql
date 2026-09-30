INSERT INTO staging.stg_orders
SELECT id, customer_id, amount, created_at
FROM raw.orders;
