# gRPC and Protobuf API design rules

Back to [API Design Principles](../README.md) | Web version: [grpc-and-protobuf-api-design.html](https://api-design-tools.github.io/api-design-principles/grpc-and-protobuf-api-design.html)

Internal microservices benefit from gRPC over HTTP/2 when sub-millisecond serialization, bi-directional streaming, or strict generated SDKs across Go, Rust, Python, and Java matter more than browser or CDN caching (`ADP-031`). Wire compatibility in Protobuf depends on field tag numbers, not field names (`ADP-042`).

## 1. Wire safety and `reserved` field tags (`ADP-042`)

Never delete a field and reuse its number. Once serialized binary messages cross process or queue boundaries, changing a tag or its wire type corrupts old readers silently:

```protobuf
syntax = "proto3";
package orders.v1;

message Order {
  reserved 4, 7;
  reserved "legacy_status", "float_total";

  string id = 1;
  int64 amount_minor = 2;
  string currency = 3;
  OrderStatus status = 5;
}
```

Run `buf breaking --against '.git#branch=main'` in CI so accidental wire breaks fail pull requests before merge.

## 2. Explicit package versioning and deadlines

Put a major version suffix in every Protobuf package (`orders.v1`, `orders.v2`), matching REST URI major versioning (`ADP-004`). Every outbound gRPC client call must also attach a deadline in context:

| Parameter | Recommended setting | Failure prevented |
| :--- | :--- | :--- |
| RPC deadline | Caller budget (for example `1500ms`) minus hop overhead | Cascading thread exhaustion across service hops |
| Enum zero value | `ORDER_STATUS_UNSPECIFIED = 0` | Distinguishes unset proto3 default from a valid domain state |
| Error mapping | `google.rpc.Status` + `ErrorInfo` metadata | Propagates machine-readable codes instead of raw stack traces |
| Money fields | `int64 units` + `int32 nanos` or `int64 amount_minor` + ISO 4217 string | Avoids IEEE 754 float drift (`ADP-029`) |

## 3. When to expose REST alongside gRPC

Browsers, third-party webhook consumers, and OpenAPI-driven AI tool runners integrate far more easily over HTTP/JSON. Keep gRPC for east-west service traffic and generate a typed REST/OpenAPI gateway at the public perimeter using Envoy JSON transcoding or `grpc-gateway`.
