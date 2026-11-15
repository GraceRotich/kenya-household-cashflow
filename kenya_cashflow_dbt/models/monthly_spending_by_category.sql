-- Spending amounts by month, expense category and payment group.
-- Keep credit and in-kind activity separate from monetary transactions.
{{ config(materialized='view') }}

SELECT
    month_start,
    category,
    payment_group,
    COUNT(DISTINCT hh_ids) AS households,
    SUM(transactions) AS transaction_count,
    SUM(amount_kes) AS recorded_amount_kes,
    SUM(missing_amounts) AS missing_amounts
FROM {{ source('financial_diaries', 'spending_monthly') }}
GROUP BY month_start, category, payment_group
