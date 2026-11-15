-- Weekly inflows, outflows and margins across recorded household-weeks.
-- A negative margin is not proof of financial distress.
{{ config(materialized='view') }}

SELECT
    week_start,
    COUNT(*) AS household_weeks,
    COUNT(DISTINCT hh_ids) AS households,
    SUM(inflows_kes) AS total_inflows_kes,
    SUM(outflows_kes) AS total_outflows_kes,
    SUM(margin_kes) AS total_margin_kes,
    SUM(recorded_days) AS recorded_household_days,
    SUM(active_days) AS active_household_days,
    SUM(negative_days) AS negative_household_days,
    SUM(CASE WHEN transactions > 0 AND margin_kes < 0 THEN 1 ELSE 0 END)
        AS negative_weeks
FROM {{ source('financial_diaries', 'household_weekly') }}
GROUP BY week_start
