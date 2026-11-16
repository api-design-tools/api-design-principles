# API Error Handling with RFC 9457 Problem Details & HTTP Status Codes (2026)

> **Back to Directory:** [API Design Principles & OpenAPI Validator](../README.md) • **Interactive Web Guide:** [error-handling-rfc9457.html](https://api-design-tools.github.io/api-design-principles/error-handling-rfc9457.html)

Returning `200 OK` with `{ "success": false, "error": "Invalid" }` breaks HTTP caching, API gateway metrics, and retry middleware. **RFC 9457** (which obsoletes RFC 7807) defines the standard `application/problem+json` error format enforced by rules `ADP-008` and `ADP-009`.

---

## 1. RFC 9457 Problem Details Structure (`ADP-008`)

Every `4xx` and `5xx` error response should return `Content-Type: application/problem+json` with these canonical members:

```http
HTTP/1.1 422 Unprocessable Content
Content-Type: application/problem+json
X-Request-Id: req_01J9Z8X2M9K4

{
  "type": "https://api.example.com/errors/validation-error",
  "title": "Your request parameters did not validate",
  "status": 422,
  "detail": "Field 'items[0].quantity' must be an integer >= 1.",
  "instance": "/v1/orders#req_01J9Z8X2M9K4",
  "errors": [
    {
      "pointer": "/items/0/quantity",
      "code": "min_value",
      "message": "Must be >= 1"
    }
  ]
}
```

| Field | Required? | Purpose |
| :--- | :---: | :--- |
| `type` | Recommended | Stable URI identifying the error category (machine-readable) |
| `title` | Recommended | Short, human-readable summary of the problem type (constant per `type`) |
| `status` | Recommended | Exact HTTP status code (`400`, `401`, `404`, `409`, `422`, `429`, `500`) |
| `detail` | Optional | Occurrence-specific explanation (never expose SQL errors or stack traces) |
| `instance` | Optional | Request URI or correlation ID reference for support/debugging |

---

## 2. HTTP Status Code Decision Cheat Sheet

| Status | Meaning | When to Return It | Client Retry Safe? |
| :--- | :--- | :--- | :---: |
| `200 OK` | Success with payload | `GET`, `PATCH`, `PUT` synchronous completion | — |
| `201 Created` | New resource persisted | `POST` creating a resource (include `Location` header) | — |
| `202 Accepted` | Queued asynchronously | Long-running exports/jobs (`ADP-026`) | — |
| `204 No Content` | Success with empty body | `DELETE` completion | — |
| `400 Bad Request` | Malformed syntax / JSON | Invalid JSON, missing required header, unknown query param | ❌ Fix request |
| `401 Unauthorized` | Unauthenticated | Missing, expired, or invalid Bearer token / signature | 🔄 Refresh token |
| `403 Forbidden` | Authenticated, lacks rights | Valid token, missing scope/permission | ❌ Do not retry |
| `404 Not Found` | Resource missing (or hidden) | Non-existent ID or tenant-scoped BOLA isolation (`ADP-023`) | ❌ Do not retry |
| `409 Conflict` | State / idempotency conflict | Duplicate unique key or mismatched `Idempotency-Key` body | ❌ Resolve state |
| `412 Precondition Failed` | Optimistic lock mismatch | `If-Match` ETag header does not match current resource version | 🔄 Re-fetch & retry |
| `422 Unprocessable Content` | Valid JSON, invalid domain rules | Negative quantity, invalid currency transition | ❌ Fix input |
| `429 Too Many Requests` | Rate limit exceeded | Quota exhausted; include `Retry-After` & `RateLimit-*` (`ADP-013`) | ✅ After `Retry-After` |
| `503 Service Unavailable` | Temporary overload / maintenance | Upstream dependency down; include `Retry-After` | ✅ Exponential backoff |
