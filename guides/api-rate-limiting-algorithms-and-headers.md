# API rate limiting algorithms and headers

Back to [API Design Principles](../README.md) | Web version: [api-rate-limiting-algorithms-and-headers.html](https://api-design-tools.github.io/api-design-principles/api-rate-limiting-algorithms-and-headers.html)

Rate limits protect origin databases from accidental retry loops and credential-stuffing spikes (`ADP-013`). Clear headers also let SDKs throttle themselves cleanly before hitting HTTP `429`.

## 1. Standard headers (`RateLimit` and `Retry-After`)

Document `429 Too Many Requests` (`application/problem+json`) along with response headers (`ADP-013`) in your OpenAPI specification:

```http
HTTP/1.1 429 Too Many Requests
Content-Type: application/problem+json
Retry-After: 12
RateLimit-Limit: 120
RateLimit-Remaining: 0
RateLimit-Reset: 12

{
  "type": "https://api.example.com/errors/rate-limited",
  "title": "Too Many Requests",
  "status": 429,
  "detail": "Tenant quota of 120 requests/minute exceeded. Retry after 12 seconds.",
  "instance": "/v1/orders"
}
```

Publish `RateLimit-Limit`, `RateLimit-Remaining`, and `RateLimit-Reset` (seconds until bucket reset, integer) on successful `200`/`201` responses as well, so automated jobs pace calls dynamically.

## 2. Algorithm tradeoffs in Redis or API gateways

| Algorithm | Memory per caller | Burst tolerance | Best suited for |
| :--- | :--- | :--- | :--- |
| Fixed Window Counter | 1 counter per window | Allows 2x boundary spikes at minute rollover | Coarse DoS protection at CDN edges |
| Sliding Window Counter | 2 counters (current + previous window) | Smooths rollover spikes with minimal Redis keys | General REST API quotas per tenant or key |
| Token Bucket | 2 fields (tokens + last refill timestamp) | Supports deliberate short bursts up to bucket capacity | Interactive webhooks, CLI sync tools, SDK batches |
| Concurrency Semaphores | Active in-flight set or counter | Caps slow simultaneous queries | Heavy exports, report generators, LLM inference endpoints |

Key rate limits by authenticated `tenant_id` or API key hash first, falling back to source IP only on unauthenticated endpoints such as login or token exchange. Always fail closed or apply a tight fallback limit on auth routes, while considering fail-open metrics alerts on non-critical read traffic if Redis blips.
