---
type: 'BigQuery Table'
title: 'products'
description: 'Products table. Each row is a product with its name, price, and category.'
tags: ['sales', 'analytics']
timestamp: '2026-06-22T00:00:00Z'
resource: 'https://console.cloud.google.com/bigquery?project=okf-analytics&p=okf-analytics&d=analytics&t=products&page=table'
---

# products

Product catalog of the sales system.

## Schema

| Column    | Type      | Description                                  |
|-----------|-----------|----------------------------------------------|
| id        | STRING    | Unique product identifier (PK)               |
| name      | STRING    | Product name                                 |
| price     | NUMERIC   | Unit price                                   |
| category  | STRING    | Product category                             |

## Example

```json
{"id": "prod_7", "name": "Notebook A5", "price": 4.50, "category": "stationery"}
```