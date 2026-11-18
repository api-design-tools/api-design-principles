# Batch and bulk APIs with 207 partial failures

Back to [API Design Principles](../README.md) | Web version: [batch-bulk-apis-and-partial-failures.html](https://api-design-tools.github.io/api-design-principles/batch-bulk-apis-and-partial-failures.html)

When callers sync 50 orders in one round trip, returning a single `200 OK` or failing the entire batch on item 37 forces wasteful individual fallbacks (`ADP-039`). Cap batch array sizes tightly (`ADP-021`, `ADP-039`) and report per-item outcomes deterministically.

## 1. Custom batch action and array bounds (`ADP-039`)

Use a `:batch` custom method suffix for multi-record operations (`POST /v1/orders:batch`) and cap the input array (`maxItems <= 100`) so requests finish well inside gateway timeouts:

```json
{
  "items": [
    { "client_ref": "row_1", "sku": "SKU-PRO", "quantity": 1 },
    { "client_ref": "row_2", "sku": "INVALID", "quantity": 0 }
  ]
}
```

## 2. Returning `207 Multi-Status` for mixed outcomes

When item 1 succeeds and item 2 fails validation, respond with HTTP `207 Multi-Status` (or `202 Accepted` for async bulk jobs per `ADP-026`) and preserve input ordering plus caller-supplied `client_ref` correlation keys:

```json
{
  "succeeded": 1,
  "failed": 1,
  "results": [
    { "index": 0, "client_ref": "row_1", "status": 201, "id": "ord_01J9Z" },
    {
      "index": 1,
      "client_ref": "row_2",
      "status": 422,
      "error": {
        "type": "https://api.example.com/errors/validation",
        "title": "Validation Failed",
        "status": 422,
        "detail": "quantity must be >= 1"
      }
    }
  ]
}
```

| Payload scale | HTTP pattern | Recommended limits |
| :--- | :--- | :--- |
| Synchronous micro-batch | `POST /v1/orders:batch` -> `207 Multi-Status` | Up to 100 items, sub-5s server deadline, `Idempotency-Key` supported |
| Asynchronous bulk import | `POST /v1/order-imports` -> `202 Accepted` (`ADP-026`) | Presigned object URL or NDJSON stream + `/v1/jobs/{job_id}` polling |
