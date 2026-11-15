-- One financial-activity type per month in the reporting model.
SELECT month_start, financial_activity, COUNT(*) AS copies
FROM {{ ref('monthly_financial_activity') }}
GROUP BY month_start, financial_activity
HAVING COUNT(*) > 1
