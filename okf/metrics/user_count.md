---
type: 'Metric'
title: 'user_count'
description: 'Daily active users (DAU) metric: number of distinct customers with activity each day.'
tags: ['sales', 'analytics']
timestamp: '2026-06-22T00:00:00Z'
resource: 'https://console.cloud.google.com/bigquery?project=okf-analytics'
---

# user_count

Daily active users (DAU) from the `orders` table as an activity proxy.

## Definition

```sql
SELECT
  DATE(created_at) AS day,
  COUNT(DISTINCT customer_id) AS user_count
FROM analytics.orders
GROUP BY 1
ORDER BY 1
```

## Example

```json
{"day": "2026-06-21", "user_count": 318}
```