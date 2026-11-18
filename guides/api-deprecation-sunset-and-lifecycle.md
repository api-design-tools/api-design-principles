# API deprecation, Sunset headers, and lifecycle

Back to [API Design Principles](../README.md) | Web version: [api-deprecation-sunset-and-lifecycle.html](https://api-design-tools.github.io/api-design-principles/api-deprecation-sunset-and-lifecycle.html)

Shutting down an endpoint without machine-readable advance signals turns routine maintenance into customer outages (`ADP-018`, `ADP-044`). Standards-compliant HTTP headers let gateways, monitors, and SDKs surface warnings months before traffic is blocked.

## 1. Combining RFC 9745 `Deprecation` and RFC 8594 `Sunset`

When flagging an operation with `"deprecated": true` in OpenAPI (`ADP-018`), return both deprecation and shutdown timestamps plus a migration link:

```http
HTTP/1.1 200 OK
Deprecation: @1794873600
Sunset: Sat, 15 May 2027 00:00:00 GMT
Link: <https://api.example.com/docs/migrate-v2>; rel="deprecation"
Content-Type: application/json
```

Note the header formats defined by the two RFCs: `Deprecation` uses an HTTP Structured Field Unix timestamp prefixed with `@` (RFC 9745), whereas `Sunset` uses an IMF-fixdate HTTP date string (RFC 8594).

## 2. Six-month lifecycle from telemetry to `410 Gone`

| Lifecycle stage | Timing | Action |
| :--- | :--- | :--- |
| Announce deprecation | T minus 6 to 12 months | Release `/v2`, mark `/v1` `deprecated: true`, start returning `Deprecation` + `Sunset` headers |
| Telemetry outreach | T minus 90 days | Group server logs by `client_id` / API key prefix and email active consumers directly |
| Scheduled brownouts | T minus 14 days | Return `410 Gone` for 15 minutes during announced maintenance windows to catch silent cron jobs |
| End of life | Sunset date | Remove route handler and return `410 Gone` (`application/problem+json`) with migration `Link` |
