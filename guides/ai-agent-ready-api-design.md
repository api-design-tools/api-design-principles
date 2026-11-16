# Designing APIs for AI Agents & MCP Tools (2026)

Back to [API Design Principles](../README.md) | Web version: [ai-agent-ready-api-design.html](https://api-design-tools.github.io/api-design-principles/ai-agent-ready-api-design.html)

Modern OpenAPI specs do not just feed Swagger UI and SDK generators. AI coding assistants and Model Context Protocol (MCP) bridges convert OpenAPI operations directly into callable tools (`ADP-017`, `ADP-019`, `ADP-032`). Ambiguous contracts cause agents to guess parameter names, retry non-idempotent writes, or misread error payloads.

## 1. What makes an OpenAPI spec deterministic for LLM tool calling

| OpenAPI Field | Human Developer Impact | AI Agent / MCP Tool Impact | Rule |
| :--- | :--- | :--- | :--- |
| `operationId` | Generated SDK method name | Becomes the exact tool name (`listOrders`, `createOrder`) | `ADP-017` |
| `summary` & `description` | Docs navigation text | Tells the model when to pick this tool over another | `ADP-017` |
| Strict `enum` & `format` | Client validation | Prevents hallucinated status strings or wrong date formats | `ADP-022` |
| `maxLength` / `maxItems` | DoS protection (`OWASP API4`) | Prevents oversized generated payloads | `ADP-021` |
| `example` payloads | Copy-paste onboarding | Shows exact ID prefixes (`ord_...`) and currency units | `ADP-019` |
| `Idempotency-Key` | Safe network retries | Prevents duplicate orders when an agent retries a timed-out call | `ADP-012` |
| `application/problem+json` | Structured error UI | Gives the model exact `detail` text to fix its next tool call | `ADP-008` |

## 2. Bad vs. agent-ready error handling

When an AI agent sends an invalid quantity, a generic `400 {"error": "bad request"}` triggers blind retries. An RFC 9457 payload tells both human clients and LLM tool loops how to recover:

```json
{
  "type": "https://api.example.com/errors/validation",
  "title": "Validation Failed",
  "status": 422,
  "detail": "items[0].quantity must be an integer between 1 and 1000 (received 0)."
}
```

## 3. Check agent-readiness with the validator

Run `api_validator.py` with the `strict-public-api` preset to enforce `operationId`, `summary`, `example` payloads, `Idempotency-Key`, and RFC 9457 errors in one pass:

```bash
python3 api_validator.py --spec examples/orders-api-good.openapi.json --preset strict-public-api
```
