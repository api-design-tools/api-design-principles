# API Versioning, Idempotency Keys & Rate Limiting (2026 Guide)

> **Back to Directory:** [API Design Principles & OpenAPI Validator](../README.md) • **Interactive Web Guide:** [versioning-idempotency-rate-limits.html](https://api-design-tools.github.io/api-design-principles/versioning-idempotency-rate-limits.html)

Production resilience depends on three contracts rarely enforced by static style guides: **safe major versioning (`ADP-004`, `ADP-018`)**, **idempotent retries (`ADP-012`)**, and **machine-readable rate limiting (`ADP-013`)**.

---

## 1. API Versioning & Graceful Deprecation (`ADP-004`, `ADP-018`, `ADP-027`)

### URI Versioning (`/v1/orders`) vs Header Versioning (`API-Version: 2026-11-01`)
- **URI Major Versioning (`/v1/...`, `/v2/...`)** is the most cache-friendly, OpenAPI-compatible default for public REST APIs.
- **Keep minor changes additive (`ADP-027`):** Adding optional response properties or new endpoints never requires a `/v2` bump. Only breaking changes (removing fields, renaming keys, changing types, tightening validation) require a new major version.
- **Communicate End-of-Life with `Deprecation` & `Sunset` Headers (`ADP-018`):**

```http
HTTP/1.1 200 OK
Deprecation: @1767225600
Sunset: Wed, 31 Dec 2026 23:59:59 GMT
Link: <https://api.example.com/v2/orders>; rel="successor-version"
```

---

## 2. Idempotency-Key Pattern for `POST` Mutations (`ADP-012`)

If a mobile or payment client sends `POST /v1/orders` and the network drops before reading the `201 Created` response, retrying without an idempotency key creates a **duplicate order or double charge**.

```http
POST /v1/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer <token>
Idempotency-Key: 019334b2-7d3a-7b8e-91c2-4a8e2e6f1100
Content-Type: application/json
```

### Server Implementation Rules
1. Require a unique client-generated UUIDv4/v7 in `Idempotency-Key` (scoped by `tenant_id + method + path + key`).
2. Store a cryptographic hash of the request payload alongside the cached HTTP status and response body for at least **24 hours**.
3. **Same key + same payload hash:** Replay the exact original `201 Created` response without re-executing business side effects.
4. **Same key + different payload hash:** Reject with `422` or `409 Conflict` (`application/problem+json`) to catch client key reuse bugs.
5. **Concurrent in-flight duplicate:** Return `409 Conflict` with `Retry-After: 1` (or wait on a distributed lock).

---

## 3. Standard Rate Limiting Headers & `429` Backoff (`ADP-013`)

Follow the **IETF RateLimit Header Fields** draft alongside `429 Too Many Requests` (RFC 6585):

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
