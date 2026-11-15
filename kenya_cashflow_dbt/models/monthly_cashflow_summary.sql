
-- Monthly financial activity across the study households (inflow and outflow of cash, and margin) aggregated by month. This is a summary table that can be used for analysis and visualization in the dashboard.
-- SQL view
{{ config(materialized='view') }}

SELECT
    month_start,
    COUNT(*) AS household_months,
    COUNT(DISTINCT hh_ids) AS households,
    SUM(inflows_kes) AS total_inflows_kes,
    SUM(outflows_kes) AS total_outflows_kes,
    SUM(margin_kes) AS total_margin_kes,
    SUM(CASE WHEN negative_month = TRUE THEN 1 ELSE 0 END) -- Count of months with negative margin. Converts true (indicator) to countable no
        AS negative_months
FROM {{ source('financial_diaries', 'household_monthly') }}
GROUP BY month_start
