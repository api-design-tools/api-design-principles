# API Error Handling with RFC 9457 Problem Details & HTTP Status Codes (2026)

Back to [API Design Principles](../README.md) | Web version: [error-handling-rfc9457.html](https://api-design-tools.github.io/api-design-principles/error-handling-rfc9457.html)

Returning `200 OK` with `{ "success": false, "error": "Invalid" }` breaks HTTP caching, API gateway metrics, and client retry middleware. RFC 9457 (which obsoletes RFC 7807) defines the standard `application/problem+json` error payload checked by rules `ADP-008` and `ADP-009`.

## 1. RFC 9457 Problem Details structure (`ADP-008`)

Return `Content-Type: application/problem+json` on `4xx` and `5xx` responses:

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

| Field | Status | Purpose |
| :--- | :---: | :--- |
| `type` | Recommended | Stable URI identifying the error category |
| `title` | Recommended | Short summary of the problem type (constant per `type`) |
| `status` | Recommended | HTTP status code (`400`, `401`, `404`, `409`, `422`, `429`, `500`) |
| `detail` | Optional | Occurrence-specific explanation without leaking SQL errors or stack traces |
| `instance` | Optional | Request URI or correlation ID reference for support debugging |

## 2. HTTP status code cheat sheet

| Status | Meaning | When to return it | Client retry safe |
| :--- | :--- | :--- | :---: |
| `200 OK` | Success with payload | `GET`, `PATCH`, `PUT` synchronous completion | No |
| `201 Created` | New resource persisted | `POST` creating a resource (include `Location` header) | No |
| `202 Accepted` | Queued asynchronously | Long-running exports or batch jobs (`ADP-026`) | No |
| `204 No Content` | Success with empty body | `DELETE` completion | No |
| `400 Bad Request` | Malformed syntax | Invalid JSON, missing required header, unknown query param | Fix request |
| `401 Unauthorized` | Unauthenticated | Missing, expired, or invalid Bearer token or signature | Refresh token |
| `403 Forbidden` | Authenticated, lacks rights | Valid token without the required OAuth scope or role | No |
| `404 Not Found` | Missing or hidden resource | Non-existent ID or tenant-scoped BOLA isolation (`ADP-023`) | No |
| `409 Conflict` | State or idempotency clash | Duplicate unique key or reused `Idempotency-Key` with different payload | Resolve state |
| `412 Precondition Failed` | Optimistic lock mismatch | `If-Match` ETag does not match current resource version | Re-fetch and retry |
| `422 Unprocessable Content` | Semantic domain error | Valid JSON syntax that violates business rules | Fix input |
| `429 Too Many Requests` | Rate limit exceeded | Quota exhausted; include `Retry-After` and `RateLimit-*` (`ADP-013`) | After `Retry-After` |
| `503 Service Unavailable` | Temporary overload | Upstream dependency down; include `Retry-After` | Exponential backoff |
