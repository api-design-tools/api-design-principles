# OWASP API security top 10 and auth design checklist (2026)

Back to [API Design Principles](../README.md) | Web version: [api-security-owasp-checklist.html](https://api-design-tools.github.io/api-design-principles/api-security-owasp-checklist.html)

Most API breaches come from missing authorization checks, unbounded inputs, or leaked credentials, not from broken TLS ciphers. This guide maps the highest-risk OWASP API Security Top 10 issues to concrete OpenAPI rules (`ADP-014`, `ADP-015`, `ADP-016`, `ADP-021`, `ADP-023`, `ADP-024`, `ADP-034`, `ADP-035`).

## 1. Automated OpenAPI security checks (`--preset owasp-api-top10`)

Run the OWASP security profile directly against your spec:

```bash
python3 api_validator.py --spec examples/orders-api-good.openapi.json --preset owasp-api-top10
```

| Rule | OWASP Category | What the validator checks | Fix |
| :--- | :--- | :--- | :--- |
| `ADP-014` | API8:2023 Security Misconfiguration | Rejects non-local `http://` server URLs | Use `https://` with TLS 1.2+ |
| `ADP-015` | API2:2023 Broken Authentication | Flags missing `components.securitySchemes` or unprotected operations | Declare `BearerAuth` / OAuth 2.1 and apply globally or per route |
| `ADP-016` | API2:2023 Broken Authentication | Flags `api_key`, `token`, `secret`, `password` in query parameters | Move credentials into `Authorization` headers |
| `ADP-021` | API4:2023 Unrestricted Resource Consumption | Flags input strings without `maxLength` and arrays without `maxItems` | Add `maxLength` and `maxItems` |
| `ADP-034` | API4:2023 Unrestricted Resource Consumption | Flags integer or numeric query parameters and fields without bounds | Add `minimum` and `maximum` |
| `ADP-035` | API3:2023 Broken Object Property Level Auth | Flags input object schemas without `additionalProperties: false` | Disallow undeclared properties on request DTOs |
| `ADP-010` | API4:2023 Unrestricted Resource Consumption | Flags collection `GET` endpoints with no pagination parameters | Require `cursor` and bounded `limit` (e.g. `maximum: 100`) |

## 2. Object-level authorization (BOLA / IDOR, `ADP-023`)

Authentication tells you who sent the request. Authorization tells you whether that caller owns `/v1/orders/{order_id}`. Every database lookup for a tenant-scoped resource must include the authenticated principal or tenant ID in the predicate:

```sql
-- Vulnerable: trusts the path ID alone
SELECT * FROM orders WHERE id = $1;

-- Safe: scoped to the authenticated tenant
SELECT * FROM orders WHERE id = $1 AND tenant_id = $2;
```

Return `404 Not Found` consistently when a caller requests another tenant's resource if you want to avoid confirming that the ID exists.

## 3. Opaque prefixed identifiers (`ADP-024`)

Sequential integers (`/v1/invoices/1042`) expose order volume and let scripts enumerate records. Prefer prefixed UUIDv7 (`RFC 9562`) or ULID values such as `inv_01J9Z4K8M2P7X3Q9W5V`. They remain sortable in B-Tree indexes while hiding row counts.
