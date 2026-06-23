---
type: 'BigQuery Table'
title: 'orders'
description: 'Orders table. Each row is an order placed by a customer, with its total and creation date.'
tags: ['sales', 'analytics']
timestamp: '2026-06-22T00:00:00Z'
resource: 'https://console.cloud.google.com/bigquery?project=okf-analytics&p=okf-analytics&d=analytics&t=orders&page=table'
---

# orders

Orders table of the sales system.

## Schema

| Column        | Type       | Description                                  |
|---------------|------------|----------------------------------------------|
| id            | STRING     | Unique order identifier (PK)                |
| customer_id   | STRING     | FK to `customers.id`                         |
| total         | NUMERIC    | Total order amount                           |
| created_at    | TIMESTAMP  | Order creation date and time                 |

## Example

```json
{"id": "ord_001", "customer_id": "cus_42", "total": 129.90, "created_at": "2026-06-21T10:32:00Z"}
```