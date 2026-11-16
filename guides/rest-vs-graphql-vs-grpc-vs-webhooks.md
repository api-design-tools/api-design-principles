# REST vs GraphQL vs gRPC vs Webhooks & SSE (2026)

Back to [API Design Principles](../README.md) | Web version: [rest-vs-graphql-vs-grpc.html](https://api-design-tools.github.io/api-design-principles/rest-vs-graphql-vs-grpc.html)

Matching the API style (`ADP-031`) to consumer needs avoids forcing internal gRPC patterns onto public developer APIs or exposing unconstrained GraphQL introspection to third parties.

## 1. Protocol comparison

| Dimension | REST (OpenAPI 3.1) | GraphQL | gRPC (Protobuf) | Webhooks / SSE |
| :--- | :--- | :--- | :--- | :--- |
| Primary use case | Public developer APIs, SaaS, CRUD, CDN-cached reads | Multi-entity web/mobile UI aggregation (BFF) | Low-latency internal microservice RPC | Async event delivery (`Webhooks`) and AI token streams (`SSE`) |
| Transport and payload | HTTP/1.1 to HTTP/3 + JSON | HTTP `POST` + JSON query/response | HTTP/2 + Binary Protobuf | HTTP `POST` callbacks / `text/event-stream` |
| HTTP edge caching | Native (`ETag`, `Cache-Control`) | Needs persisted `GET` queries + CDN setup | Not HTTP-cacheable | Push / stream only |
| Schema contract | OpenAPI 3.1 + JSON Schema | GraphQL SDL | `.proto` (Protobuf v3) | OpenAPI `webhooks` + Standard Webhooks |
| Required guardrails | `api_validator.py` (`ADP-001`..`022`) | Persisted queries, depth/cost limits, disable prod introspection | Backwards-compatible field numbers, mTLS | HMAC-SHA256 signatures + 5-min replay window (`ADP-025`) |
| AI / MCP tool fit | Direct 1-to-1 OpenAPI to tool mapping | Needs curated query wrappers | Needs gRPC-Gateway transcoding | SSE powers remote MCP and streaming agents |

## 2. Typical multi-protocol architecture

External partner APIs work best as REST + OpenAPI 3.1 validated in CI with `api_validator.py`. Internal service-to-service hops can stay on gRPC with Protobuf breaking-change lint. UI screens that aggregate five or more downstream services can sit behind a GraphQL BFF using persisted queries, while outbound notifications use HMAC-signed webhooks with exponential backoff.
