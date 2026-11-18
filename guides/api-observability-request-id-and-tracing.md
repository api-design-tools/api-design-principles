# API observability, X-Request-Id, and distributed tracing

Back to [API Design Principles](../README.md) | Web version: [api-observability-request-id-and-tracing.html](https://api-design-tools.github.io/api-design-principles/api-observability-request-id-and-tracing.html)

Support tickets rarely include raw microservice logs. Returning a deterministic correlation ID in response headers (`X-Request-Id`) and error bodies alongside W3C `traceparent` propagation connects a client error straight to a distributed trace (`ADP-030`).

## 1. Request IDs and W3C `traceparent` headers (`ADP-030`)

Accept an optional client-supplied `X-Request-Id` (sanitized to alphanumeric plus `-`/`_`, max 64 chars) or generate a prefixed ULID/UUID on ingress:

```http
HTTP/1.1 500 Internal Server Error
Content-Type: application/problem+json
X-Request-Id: req_01J9Z4K8M2P7X3Q9W5V
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01

{
  "type": "https://api.example.com/errors/internal",
  "title": "Internal Server Error",
  "status": 500,
  "detail": "Upstream ledger timeout. Share request_id req_01J9Z4K8M2P7X3Q9W5V with support.",
  "instance": "/v1/orders?request_id=req_01J9Z4K8M2P7X3Q9W5V"
}
```

Echo `X-Request-Id` on both `2xx` responses and `4xx`/`5xx` error responses. Validator rule `ADP-030` checks OpenAPI operations for `X-Request-Id`, `Request-Id`, or `traceparent` headers.

## 2. Operational endpoints (`/healthz`, `/readyz`) and log redaction

| Endpoint or field | Purpose | Design rule |
| :--- | :--- | :--- |
| `GET /healthz` | Liveness probe for orchestrator restarts | Never touch downstream databases; return `200` if process event loop responds |
| `GET /readyz` | Readiness probe for load balancer traffic | Verify DB pool and critical dependencies; exempt from business `/v1` versioning |
| Structured logs | Machine-parsable JSON logs | Redact `Authorization`, cookies, `client_secret`, and card PANs before emit |
