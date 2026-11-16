# REST API Naming Conventions & HTTP Method Semantics (2026)

Back to [API Design Principles](../README.md) | Web version: [rest-naming-and-methods.html](https://api-design-tools.github.io/api-design-principles/rest-naming-and-methods.html)

Static API style guides tell developers to use nouns instead of verbs, yet production OpenAPI specs still ship with `/getUserOrders/`, `/createOrder`, and `GET` endpoints carrying JSON request bodies. This reference pairs **RFC 9110** rules with automated OpenAPI checks (`ADP-001` through `ADP-007`, `ADP-020`).

## 1. Resource naming rules (`ADP-001`, `ADP-002`, `ADP-003`)

| Rule ID | Principle | Bad URI | Good URI | Why it matters |
| :--- | :--- | :--- | :--- | :--- |
| `ADP-001` | Plural nouns, no CRUD verbs | `/v1/getUsers`, `/v1/createOrder` | `/v1/users`, `/v1/orders` | HTTP method already conveys the action |
| `ADP-002` | Lowercase `kebab-case` | `/v1/paymentMethods/{id}`, `/v1/order_items` | `/v1/payment-methods/{payment_method_id}` | Prevents case-sensitivity and cache-key splits |
| `ADP-003` | No trailing slashes | `/v1/orders/` | `/v1/orders` | Avoids 301 redirects that drop `POST` bodies |
| `ADP-004` | Major version prefix | `/orders` | `/v1/orders` | Isolates breaking schema changes cleanly |

When an operation does not map cleanly to `POST`, `PATCH`, or `DELETE` on a resource (such as `cancel`, `refund`, or `search`), use either a sub-resource noun (`POST /v1/orders/{order_id}/cancellations`) or a **Google AIP-136** custom method suffix (`POST /v1/orders/{order_id}:cancel`).

## 2. HTTP method semantics

| Method | Safe | Idempotent | Request body allowed | Typical success status | Rule |
| :--- | :---: | :---: | :--- | :--- | :--- |
| `GET` | Yes | Yes | Never (`ADP-005`) | `200 OK` / `304 Not Modified` | `ADP-005` |
| `HEAD` | Yes | Yes | Never (`ADP-005`) | `200 OK` (headers only) | `ADP-005` |
| `POST` | No | No (use `Idempotency-Key`) | Required | `201 Created` (`Location`) or `202 Accepted` | `ADP-007`, `ADP-012` |
| `PUT` | No | Yes (full replace) | Required | `200 OK` / `204 No Content` (use `If-Match`) | `ADP-020` |
| `PATCH` | No | Depends (`merge-patch` is idempotent) | Required | `200 OK` (`application/merge-patch+json`) | `ADP-020` |
| `DELETE` | No | Yes | Avoid (`ADP-006`) | `204 No Content` / `202 Accepted` | `ADP-006` |

`PUT /v1/orders/{order_id}` replaces the full resource representation. If a caller omits a field, the server clears or rejects it, so pair `PUT` with `ETag` and `If-Match` to prevent lost concurrent updates. For partial updates, use `PATCH` with `Content-Type: application/merge-patch+json` (RFC 7396):

```http
PATCH /v1/orders/ord_01J9Z4K8M2 HTTP/1.1
Host: api.example.com
Authorization: Bearer <token>
Content-Type: application/merge-patch+json
If-Match: "etag-v3"

{
  "status": "cancelled"
}
```

## 3. Validate naming and methods automatically

```bash
python3 api_validator.py --spec examples/orders-api-bad.openapi.json --format markdown
```
