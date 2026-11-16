# API Pagination, Filtering & Sorting Design Guide (2026)

> **Back to Directory:** [API Design Principles & OpenAPI Validator](../README.md) • **Interactive Web Guide:** [pagination-and-filtering.html](https://api-design-tools.github.io/api-design-principles/pagination-and-filtering.html)

Unbounded collection endpoints (`GET /v1/orders` returning every row in PostgreSQL) are the #1 cause of API latency spikes and **OWASP API4:2023 (Unrestricted Resource Consumption)** outages. This guide compares cursor pagination vs. offset pagination and shows how rules `ADP-010`, `ADP-011`, and `ADP-021` enforce safe bounds in OpenAPI.

---

## 1. Cursor (Keyset) Pagination vs. Offset Pagination

| Dimension | Cursor / Keyset Pagination (`?cursor=...&limit=25`) | Offset Pagination (`?offset=5000&limit=25`) |
| :--- | :--- | :--- |
| **SQL Query Pattern** | `WHERE (created_at, id) < ($1, $2) ORDER BY created_at DESC, id DESC LIMIT 25` | `ORDER BY created_at DESC OFFSET 5000 LIMIT 25` |
| **Database Time Complexity** | **O(1)** via composite B-Tree index seek | **O(N)** — database scans and discards all `N` offset rows |
| **Real-Time Consistency** | **Stable** — new inserts never cause duplicate rows across pages | **Drifts** — inserting a row shifts offsets and duplicates items |
| **Random Page Jump (`page=47`)** | Not directly supported (use next/prev cursors) | Supported for small admin tables (`< 10,000` rows) |
| **Validator Rule** | Recommended (`ADP-010` pass) | Flagged (`ADP-011` warning if used without cursor) |

---

## 2. Standard Cursor Pagination Envelope

Encode the opaque cursor as URL-safe Base64 (never expose raw SQL predicates to clients) and enforce a hard `maximum` on `limit`:

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

### OpenAPI 3.1 Parameter Constraints (`ADP-010`, `ADP-021`)
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

---

## 3. Filtering & Sorting Conventions

- **Simple Equality & Range Filters:** Use clear query keys with explicit operator suffixes when needed:
  `GET /v1/orders?status=paid&created_after=2026-11-01T00:00:00Z`
- **Multi-Value Filters:** Comma-separated or repeated parameters (`?status=paid,shipped`), bounded with `enum` and `maxItems`.
- **Deterministic Sorting:** Always include a unique tie-breaker column (`id`) in `ORDER BY`:
  `GET /v1/orders?sort=-created_at,id` (`-` prefix for descending).
- **Reject Unknown Filter Keys in Strict APIs:** Return `400 Bad Request` (`application/problem+json`) rather than silently ignoring typos like `?stauts=paid`.
