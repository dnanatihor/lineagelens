CREATE TABLE analytics.flagged AS
SELECT
  id,
  CASE WHEN status = 'cancelled' THEN 0 ELSE amount END AS net_amount
FROM raw.orders;
