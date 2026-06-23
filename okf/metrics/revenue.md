---
type: 'Metric'
title: 'revenue'
description: 'Revenue metric: monthly sum of the total of all closed orders.'
tags: ['sales', 'analytics']
timestamp: '2026-06-22T00:00:00Z'
resource: 'https://console.cloud.google.com/bigquery?project=okf-analytics'
---

# revenue

Monthly sum of sales from the `orders` table.

## Definition

```sql
SELECT
  DATE_TRUNC(created_at, MONTH) AS month,
  SUM(total) AS revenue
FROM analytics.orders
GROUP BY 1
ORDER BY 1
```

## Example

```json
{"month": "2026-06", "revenue": 42810.75}
```