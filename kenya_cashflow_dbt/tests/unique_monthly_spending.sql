-- One category/payment group row per month in the reporting model.
SELECT month_start, category, payment_group, COUNT(*) AS copies
FROM {{ ref('monthly_spending_by_category') }}
GROUP BY month_start, category, payment_group
HAVING COUNT(*) > 1
