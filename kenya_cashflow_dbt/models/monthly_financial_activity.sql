-- Summary of recorded deposits, withdrawals, borrowing and repayments.
-- These amounts are financial-device activity, not net household savings.
{{ config(materialized='view') }}

SELECT
    month_start,
    financial_activity,
    COUNT(DISTINCT hh_ids) AS households,
    SUM(transactions) AS transaction_count,
    SUM(amount_kes) AS recorded_amount_kes,
    SUM(missing_amounts) AS missing_amounts
FROM {{ source('financial_diaries', 'financial_monthly') }}
GROUP BY month_start, financial_activity
