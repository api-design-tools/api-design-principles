# API versioning, idempotency keys, and rate limiting (2026)

Back to [API Design Principles](../README.md) | Web version: [versioning-idempotency-rate-limits.html](https://api-design-tools.github.io/api-design-principles/versioning-idempotency-rate-limits.html)

Production resilience depends on three contracts often skipped in static style guides: major versioning (`ADP-004`, `ADP-018`), idempotent retries (`ADP-012`), and machine-readable rate limits (`ADP-013`).

## 1. API versioning and deprecation (`ADP-004`, `ADP-018`, `ADP-027`)

URI major versioning (`/v1/orders`, `/v2/orders`) works reliably with CDN caches, OpenAPI routers, and client SDKs. Keep minor updates additive (`ADP-027`): adding optional response fields or new endpoints stays on `/v1`, while renaming fields, changing types, or tightening inputs belongs in `/v2`.

When retiring an endpoint, expose `Deprecation` (RFC 9745) and `Sunset` (RFC 8594) headers:

```http
HTTP/1.1 200 OK
Deprecation: @1767225600
Sunset: Wed, 31 Dec 2026 23:59:59 GMT
Link: <https://api.example.com/v2/orders>; rel="successor-version"
```

## 2. Idempotency-Key pattern for `POST` mutations (`ADP-012`)

If a client sends `POST /v1/orders` and drops the connection before reading `201 Created`, retrying without an idempotency key creates a duplicate order or double charge.

```http
POST /v1/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer <token>
Idempotency-Key: 019334b2-7d3a-7b8e-91c2-4a8e2e6f1100
Content-Type: application/json
```

Server rules for handling `Idempotency-Key`:
1. Scope keys by `(tenant_id, method, path, key)` and store a SHA-256 hash of the request payload alongside the cached response for at least 24 hours.
2. Same key and matching payload hash: replay the original `201 Created` response without re-running business side effects.
3. Same key and different payload hash: return `409 Conflict` or `422` (`application/problem+json`) so client key-reuse bugs fail loudly.
4. Concurrent in-flight request with the same key: return `409 Conflict` with `Retry-After: 1` (or wait on a short distributed lock).

## 3. Rate limit headers and `429` backoff (`ADP-013`)

Follow the IETF RateLimit Header Fields draft alongside `429 Too Many Requests` (RFC 6585):

```http
HTTP/1.1 429 Too Many Requests
Content-Type: application/problem+json
Retry-After: 15
RateLimit-Limit: 120
RateLimit-Remaining: 0
RateLimit-Reset: 15

{
  "type": "https://api.example.com/errors/rate-limited",
  "title": "Too Many Requests",
  "status": 429,
  "detail": "Plan limit of 120 requests/minute exceeded. Retry after 15 seconds."
}
```
