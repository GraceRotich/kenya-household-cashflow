-- One row per household, useful for comparisons and dashboard filters.
-- These are totals for the recorded months only (not annualized averages).
{{ config(materialized='view') }}

SELECT
    hh_ids,
    COUNT(*) AS recorded_months,
    SUM(inflows_kes) AS total_inflows_kes,
    SUM(outflows_kes) AS total_outflows_kes,
    SUM(margin_kes) AS total_margin_kes,
    SUM(CASE WHEN negative_month = TRUE THEN 1 ELSE 0 END) AS negative_months,
    SUM(CASE WHEN transactions > 0 THEN 1 ELSE 0 END) AS active_months
FROM {{ source('financial_diaries', 'household_monthly') }}
GROUP BY hh_ids
