# API pagination, filtering, and sorting design (2026)

Back to [API Design Principles](../README.md) | Web version: [pagination-and-filtering.html](https://api-design-tools.github.io/api-design-principles/pagination-and-filtering.html)

Unbounded collection endpoints (`GET /v1/orders` returning every row in PostgreSQL) cause memory spikes, slow table scans, and OWASP API4:2023 (Unrestricted Resource Consumption) outages. Rules `ADP-010`, `ADP-011`, and `ADP-021` enforce safe pagination bounds in OpenAPI specs.

## 1. Cursor (keyset) pagination vs. offset pagination

| Dimension | Cursor / keyset pagination (`?cursor=...&limit=25`) | Offset pagination (`?offset=5000&limit=25`) |
| :--- | :--- | :--- |
| SQL query pattern | `WHERE (created_at, id) < ($1, $2) ORDER BY created_at DESC, id DESC LIMIT 25` | `ORDER BY created_at DESC OFFSET 5000 LIMIT 25` |
| Database complexity | O(1) via composite B-Tree index seek | O(N), scans and discards all N offset rows |
| Concurrent write stability | Stable, new inserts do not duplicate items across pages | Drifts, inserting a row shifts offsets and duplicates items |
| Random page jumps (`page=47`) | Not directly supported | Supported for small admin tables (< 10,000 rows) |
| Validator rule | Recommended (`ADP-010` pass) | Triggers `ADP-011` warning if used without a cursor |

## 2. Standard cursor pagination envelope

Encode the cursor as URL-safe Base64 so clients treat it as an opaque token, and cap `limit` with `minimum` and `maximum`:

```http
GET /v1/orders?limit=25&cursor=eyJjcmVhdGVkX2F0IjoiMjAyNi0xMS0xNlQxMDowMDowMFoiLCJpZCI6Im9yZF8wMUo5WjQifQ HTTP/1.1
Host: api.example.com
Authorization: Bearer <token>
```

```json
{
  "data": [
    {
      "id": "ord_01J9Z4K8M2P7X3Q9W5V",
      "status": "paid",
      "amount_minor": 4990,
      "currency": "USD",
      "created_at": "2026-11-16T10:00:00Z"
    }
  ],
  "next_cursor": "eyJjcmVhdGVkX2F0IjoiMjAyNi0xMS0xNlQwOTo1NTowMFoiLCJpZCI6Im9yZF8wMUo5WjEifQ",
  "has_more": true
}
```

```json
{
  "name": "limit",
  "in": "query",
  "required": false,
  "schema": {
    "type": "integer",
    "minimum": 1,
    "maximum": 100,
    "default": 25
  }
}
```

## 3. Filtering and deterministic sorting

Use clear query keys with explicit operator suffixes for range filters (`?status=paid&created_after=2026-11-01T00:00:00Z`), bound multi-value enums with `maxItems`, and include a unique tie-breaker column in `ORDER BY` (`?sort=-created_at,id`). Reject unknown query keys with `400 Bad Request` (`application/problem+json`) so typos like `?stauts=paid` fail fast.
