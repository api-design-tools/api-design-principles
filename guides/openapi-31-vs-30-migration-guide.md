# OpenAPI 3.1 vs 3.0 migration guide

Back to [API Design Principles](../README.md) | Web version: [openapi-31-vs-30-migration-guide.html](https://api-design-tools.github.io/api-design-principles/openapi-31-vs-30-migration-guide.html)

OpenAPI 3.1.0 aligns completely with JSON Schema Draft 2020-12 and adds top-level webhook contracts (`ADP-040`), removing the awkward schema subset incompatibilities present in OpenAPI 3.0.x. Both `3.0.x` and `3.1.0` run cleanly in `api_validator.py`.

## 1. Key schema syntax changes between 3.0 and 3.1

| Construct | OpenAPI 3.0.3 | OpenAPI 3.1.0 | Notes |
| :--- | :--- | :--- | :--- |
| Nullable types | `nullable: true` | `type: ["string", "null"]` | `nullable` is removed in JSON Schema 2020-12 |
| Exclusive numeric bounds | `exclusiveMinimum: true`, `minimum: 0` | `exclusiveMinimum: 0` | Changed from boolean flag to numeric threshold |
| Single-value constants | `enum: ["v1"]` | `const: "v1"` | Standard JSON Schema keyword for discriminated unions |
| Webhook definitions | Workarounds via callbacks | Top-level `webhooks:` map (`ADP-040`) | First-class event contract alongside `paths:` |
| Ownership metadata (`ADP-033`) | `info.contact`, `info.license` | Adds `info.summary` + SPDX `license.identifier` | Required for clean catalog ownership |

## 2. Example top-level webhook block in OpenAPI 3.1

```yaml
openapi: 3.1.0
info:
  title: Billing API
  version: 2.0.0
  contact:
    email: api@example.com
  license:
    identifier: MIT
webhooks:
  orderPaid:
    post:
      operationId: onOrderPaid
      summary: Dispatched when an order transitions to paid
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/OrderPaidEvent"
      responses:
        "200":
          description: Webhook acknowledged
```

Run `python3 api_validator.py --spec openapi.yaml` after upgrading to confirm all media types (`ADP-037`), schema casing (`ADP-038`), and `info` metadata (`ADP-033`) remain valid.
