---
type: 'BigQuery Table'
title: 'customers'
description: 'Customers table. Each row is a customer with their name, email, and country.'
tags: ['sales', 'analytics']
timestamp: '2026-06-22T00:00:00Z'
resource: 'https://console.cloud.google.com/bigquery?project=okf-analytics&p=okf-analytics&d=analytics&t=customers&page=table'
---

# customers

Customers table of the sales system.

## Schema

| Column    | Type     | Description                                  |
|-----------|----------|----------------------------------------------|
| id        | STRING   | Unique customer identifier (PK)             |
| name      | STRING   | Customer name                                |
| email     | STRING   | Contact email                                |
| country   | STRING   | Country of residence (ISO-3166 alpha-2)     |

## Example

```json
{"id": "cus_42", "name": "Ada Lovelace", "email": "ada@example.com", "country": "GB"}
```