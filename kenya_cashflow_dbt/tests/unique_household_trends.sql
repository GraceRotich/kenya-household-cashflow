-- dbt tests pass when this query returns no rows.
-- Each household should have only one record for each calendar month.
SELECT hh_ids, month_start, COUNT(*) AS copies
FROM {{ ref('household_trends') }}
GROUP BY hh_ids, month_start
HAVING COUNT(*) > 1
