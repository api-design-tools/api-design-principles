# API caching with ETag, Cache-Control, and 304

Back to [API Design Principles](../README.md) | Web version: [api-caching-etag-and-304-guide.html](https://api-design-tools.github.io/api-design-principles/api-caching-etag-and-304-guide.html)

Explicit HTTP caching headers cut origin database load on read-heavy APIs while keeping private customer data out of shared proxy caches (`ADP-028`). Validator rule `ADP-028` checks every `GET 200` operation in OpenAPI for at least a `Cache-Control` or `ETag` response header.

## 1. Public catalogs vs private authenticated payloads

Choose directives based on tenant isolation:

| Endpoint type | `Cache-Control` header | Why |
| :--- | :--- | :--- |
| Public read catalog (`/v1/plans`) | `public, max-age=60, stale-while-revalidate=300` | Lets CDNs serve cached JSON fast and refresh asynchronously |
| Tenant-scoped mutable data (`/v1/orders/{id}`) | `private, max-age=0, must-revalidate` + `ETag` | Prevents shared proxies from storing tenant data while enabling `304` revalidation |
| Secrets, tokens, PII (`/v1/tokens`) | `no-store` | Instructs browsers and intermediaries not to write response bytes to disk or cache |

Include `Vary: Authorization` if a route sits behind any shared proxy and returns caller-dependent fields on the same URL.

## 2. Conditional GET (`If-None-Match`) and optimistic writes (`If-Match`)

Use the same `ETag` digest for both read bandwidth savings (`ADP-028`) and lost-update protection (`ADP-020`):

```http
GET /v1/orders/ord_01J9Z4K HTTP/1.1
If-None-Match: "v3-8a9d2f1c"

HTTP/1.1 304 Not Modified
ETag: "v3-8a9d2f1c"
Cache-Control: private, max-age=0, must-revalidate
```

On updates, require the client to send `If-Match: "v3-8a9d2f1c"` on `PATCH` or `PUT`. If another worker modified the row in between, return `412 Precondition Failed` (`application/problem+json`) instead of silently overwriting newer fields.
