-- One row per household-month for a drill-down chart in Metabase.
-- Keep recorded-day counts so partial months are visible.
{{ config(materialized='view') }}

SELECT
    hh_ids,
    month_start,
    inflows_kes,
    outflows_kes,
    margin_kes,
    recorded_days,
    active_days,
    negative_days,
    transactions,
    negative_month,
    negative_day_share,
    CASE
        WHEN transactions = 0 THEN 'no_core_activity'
        WHEN margin_kes < 0 THEN 'negative_margin'
        ELSE 'non_negative_margin'
    END AS margin_status
FROM {{ source('financial_diaries', 'household_monthly') }}
