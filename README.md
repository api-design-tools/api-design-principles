<div align="center">

# API Design Principles, REST Style Guide & OpenAPI Validator (2026)

**Standards-backed REST API design rules paired with a zero-dependency OpenAPI 3.0/3.1 JSON and YAML validator, breaking-change diff checker, GitHub Action, and CI violation reports.**

[![Verified Rules](https://img.shields.io/badge/API_Design_Rules-32_Standards_Backed-10b981?style=flat-square)](#-32-api-design-principles-matrix)
[![OpenAPI Linter](https://img.shields.io/badge/OpenAPI_Validator-JSON_%26_YAML-3b82f6?style=flat-square)](#-quick-start-validate-an-openapi-spec)
[![GitHub Action](https://img.shields.io/badge/GitHub_Action-CI_%26_SARIF_Ready-f59e0b?style=flat-square)](#-github-action-for-pull-requests)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg?style=flat-square)](LICENSE)

[Quick Start CLI](#-quick-start-validate-an-openapi-spec) • [GitHub Action](#-github-action-for-pull-requests) • [Live Browser Validator](https://api-design-tools.github.io/api-design-principles/) • [32 Core Rules](#-32-api-design-principles-matrix) • [Guides](#-topic-guides-and-web-pages) • [FAQ](#-frequently-asked-questions)

</div>

Most **API design principles** repositories (such as *Haufe-Lexware API Style Guide*) publish Markdown checklists for developers to read manually. Code reviewers still miss inconsistent error payloads, missing `Idempotency-Key` headers, and unbounded arrays under deadline pressure.

`api-design-principles` turns those conventions into checks you can run locally and in Pull Requests:

1. **Practical handbook** with 32 rules mapped to `RFC 9110`, `RFC 9457` (Problem Details), `RFC 8594` (Sunset), `IETF Idempotency-Key`, `IETF RateLimit`, `Google AIP`, and the `OWASP API Security Top 10`.
2. **Zero-dependency OpenAPI 3.0/3.1 validator (`api_validator.py`)** supporting both **JSON and YAML** specs in standard library Python 3.9+, plus a [browser-based validator](https://api-design-tools.github.io/api-design-principles/).
3. **Breaking-change detector (`--diff`)** to catch removed endpoints, changed property types, newly required parameters, and narrowed enums before merge.
4. **GitHub Action (`action.yml`)** with built-in industry presets (`google-aip`, `stripe-style`, `owasp-api-top10`, `strict-public-api`), Markdown Job Summaries, and **SARIF 2.1.0** output for GitHub Code Scanning.

![API Design Principles Handbook and OpenAPI Validator Preview](docs/assets/preview.svg)

## Comparison with static style guides and linters

| Capability | Static Style Guides *(Haufe-Lexware, docs)* | Generic Linters *(Spectral CLI)* | **api-design-tools / api-design-principles** |
| :--- | :---: | :---: | :---: |
| Handbook with HTTP/JSON examples | Yes (read-only) | No (write your own rules) | 32 RFC-backed rules with bad/good examples |
| OpenAPI 3.0 / 3.1 CLI (JSON + YAML) | No | Requires Node.js + npm | Zero-dependency Python 3.9+ stdlib |
| Built-in presets (`google-aip`, `stripe-style`, `owasp`) | No | External rulesets | Included in `presets/` |
| Breaking-change diff (`--diff`) | No | Separate tool needed | Built in |
| GitHub Action + SARIF 2.1.0 + Step Summary | No | Manual wiring | Built-in `action.yml` |
| Browser validator UI | No | No | Client-side GitHub Pages tool |

## Quick start: validate an OpenAPI spec

```bash
git clone https://github.com/api-design-tools/api-design-principles.git
cd api-design-principles

# Validate reference JSON and YAML specs (Score: 100/100)
python3 api_validator.py --spec examples/orders-api-good.openapi.json --fail-on warning
python3 api_validator.py --spec examples/orders-api-good.openapi.yaml --preset strict-public-api

# Inspect violations on the flawed example as Markdown
python3 api_validator.py --spec examples/orders-api-bad.openapi.json --format markdown --fail-on none

# Detect breaking contract changes between two revisions
python3 api_validator.py --diff base.openapi.yaml head.openapi.yaml --format markdown

# Export SARIF 2.1.0 for GitHub Code Scanning
python3 api_validator.py --spec openapi.json --format sarif --output api-design.sarif
```

You can also paste or upload any OpenAPI JSON or YAML file in the [Interactive Browser Validator](https://api-design-tools.github.io/api-design-principles/).

## GitHub Action for pull requests

Add `.github/workflows/api-design.yml` to block breaking changes and rule errors in Pull Requests and publish a violation report in the workflow summary:

```yaml
name: API Design Principles Check

on:
  pull_request:
    paths:
      - "**/openapi*.*"
      - ".api-rules.json"

jobs:
  api-lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Validate OpenAPI Specification
        uses: api-design-tools/api-design-principles@v1
        with:
          spec: "services/**/openapi.yaml"
          preset: "stripe-style"
          config: ".api-rules.json"
          fail-on: "error"
          report-format: "markdown"
          output-file: "api-design-report.md"
          write-summary: "true"
```

Inputs: `spec`, `preset` (`google-aip`, `stripe-style`, `owasp-api-top10`, `strict-public-api`), `config`, `diff-base`, `fail-on` (`error`, `warning`, `none`), `report-format` (`markdown`, `json`, `sarif`, `text`), `output-file`, `write-summary`. Outputs: `score` (`0-100`), `errors`, `warnings`, `passed`, `report-path`.

## 32 API design principles matrix

All 32 rules live in [`rules.json`](rules.json). Rules marked `Auto` run against OpenAPI specs in `api_validator.py`, the browser validator, and the GitHub Action.

### 1. URI naming, versioning, and HTTP methods

| ID | Mode | Severity | Principle & Standard | Bad Example | Good Example |
| :--- | :---: | :---: | :--- | :--- | :--- |
| **ADP-001** | Auto | `ERROR` | Plural resource nouns, no CRUD verbs (`RFC 9110 §9`) | `GET /v1/getOrders` | `GET /v1/orders` |
| **ADP-002** | Auto | `WARN` | Lowercase `kebab-case` URI segments (`Google AIP-122`) | `/v1/orderItems` | `/v1/order-items` |
| **ADP-003** | Auto | `WARN` | No trailing slashes (`RFC 3986`) | `GET /v1/orders/` | `GET /v1/orders` |
| **ADP-004** | Auto | `ERROR` | Explicit major API versioning (`AIP-185`) | `GET /orders` | `GET /v1/orders` |
| **ADP-005** | Auto | `ERROR` | `GET`/`HEAD` must never declare `requestBody` (`RFC 9110 §9.3.1`) | `GET` + JSON body | `GET ?status=paid` |
| **ADP-006** | Auto | `WARN` | `DELETE` returns `204`/`202`, no required body (`RFC 9110 §9.3.5`) | `DELETE` + body -> `200` | `DELETE /v1/orders/{id}` -> `204` |
| **ADP-007** | Auto | `ERROR` | `POST` creation returns `201` (`Location`) or `202` (`RFC 9110`) | `POST /v1/orders` -> `200` | `201 Created` + `Location` |
| **ADP-018** | Auto | `INFO` | `Deprecation` and `Sunset` headers (`RFC 8594` / `RFC 9745`) | `deprecated: true` only | `Sunset: Wed, 31 Dec 2026...` |
| **ADP-020** | Auto | `WARN` | `PATCH` for partial updates + `ETag`/`If-Match` (`RFC 7396`) | Unconditional `PUT` | `PATCH` + `If-Match` |

### 2. Errors (`RFC 9457`), pagination, idempotency, and rate limiting

| ID | Mode | Severity | Principle & Standard | Bad Example | Good Example |
| :--- | :---: | :---: | :--- | :--- | :--- |
| **ADP-008** | Auto | `ERROR` | Use `application/problem+json` for 4xx/5xx (`RFC 9457`) | `{ "msg": "bad" }` | `{ "type": "...", "title": "...", "status": 400 }` |
| **ADP-009** | Auto | `ERROR` | Explicit 4xx / default error responses (`OpenAPI 3.1`) | Only `200` documented | `200`, `400`, `401`, `404`, `429` |
| **ADP-010** | Auto | `ERROR` | Collection `GET` must support pagination (`OWASP API4`) | Unbounded array | `?cursor=...&limit=25` |
| **ADP-011** | Auto | `WARN` | Prefer keyset/cursor over `offset` pagination (`AIP-158`) | `?offset=50000` | `?cursor=ord_01J9Z&limit=25` |
| **ADP-012** | Auto | `ERROR` | `Idempotency-Key` on `POST` mutations (`IETF Draft`) | `POST /v1/orders` raw | `Idempotency-Key: <uuid>` |
| **ADP-013** | Auto | `WARN` | `429 Too Many Requests` + `RateLimit-*` headers (`RFC 6585`) | Undocumented throttling | `429` + `Retry-After` + `RateLimit-*` |

### 3. Security (`OWASP API Top 10`), schemas, and AI/MCP readiness

| ID | Mode | Severity | Principle & Standard | Bad Example | Good Example |
| :--- | :---: | :---: | :--- | :--- | :--- |
| **ADP-014** | Auto | `ERROR` | Enforce `https://` server URLs (`OWASP API8:2023`) | `http://api.example.com` | `https://api.example.com/v1` |
| **ADP-015** | Auto | `ERROR` | Declare `securitySchemes` and operation auth (`OWASP API2`) | Missing auth definitions | `BearerAuth` (OAuth2/JWT) |
| **ADP-016** | Auto | `WARN` | Never pass API keys or tokens in query strings (`RFC 6750`) | `?api_key=sk_live_...` | `Authorization: Bearer ...` |
| **ADP-017** | Auto | `WARN` | Unique `operationId` and concise `summary` (`OpenAPI / MCP`) | Missing/duplicate IDs | `operationId: listOrders` |
| **ADP-019** | Auto | `WARN` | Concrete `example` on media types/schemas (`OpenAPI 3.1`) | Schema without example | Concrete JSON example |
| **ADP-021** | Auto | `ERROR` | Bound strings (`maxLength`) and arrays (`maxItems`) (`OWASP API4`) | Unbounded `type: array` | `maxItems: 50`, `maxLength: 128` |
| **ADP-022** | Auto | `INFO` | ISO 8601 UTC `format: date-time` timestamps (`RFC 3339`) | `created_at: { type: string }` | `format: date-time` |
| **ADP-023..032** | Arch | `MIXED` | BOLA/IDOR scoping, UUIDv7/ULID IDs, signed webhooks, `202` async jobs, integer minor-unit money, W3C `traceparent`, REST vs GraphQL vs gRPC, MCP readiness | Raw floats, unsigned webhooks | `amount_minor` + HMAC-SHA256 |

## Sample violation report

Running `python3 api_validator.py --spec examples/orders-api-bad.openapi.json --format markdown` produces:

```markdown
## API Design Principles Validation Report

### `examples/orders-api-bad.openapi.json` (Legacy Anti-Pattern Orders API): **FAIL**, Score `0/100`

- OpenAPI Version: `3.0.3` | Operations Checked: `4`
- Violations: `22` Errors, `24` Warnings, `2` Info

| Severity | Rule | Location | Violation | Standard |
| :--- | :--- | :--- | :--- | :--- |
| `ERROR` | **ADP-014** | `servers[0].url` | Insecure HTTP server URL 'http://api.legacy-shop.internal' detected... | OWASP API8:2023 |
| `ERROR` | **ADP-001** | `/getUserOrders/` | Segment 'getUserOrders' looks like a CRUD verb; use plural resource nouns... | RFC 9110 §9 |
| `ERROR` | **ADP-005** | `GET /getUserOrders/` | GET operation declares a requestBody, which violates RFC 9110 §9.3.1. | RFC 9110 §9.3.1 |
| `ERROR` | **ADP-012** | `POST /createOrder` | POST mutation does not declare an Idempotency-Key header parameter... | IETF Idempotency |
| `ERROR` | **ADP-008** | `POST /createOrder (400)` | Error responses do not use RFC 9457 media type 'application/problem+json'. | RFC 9457 |
```

## Team rulesets and multi-repository audits

Platform teams can maintain one baseline config (see [`.api-rules.example.json`](.api-rules.example.json)) or choose a built-in preset from [`presets/`](presets):

```bash
python3 api_validator.py \
  --spec "services/*/openapi.*" \
  --preset google-aip \
  --config .api-rules.example.json \
  --format json \
  --output reports/org-api-audit.json
```

## Topic guides and web pages

| Topic | Markdown Guide | Web Version | Focus |
| :--- | :--- | :--- | :--- |
| Interactive OpenAPI Validator | [`api_validator.py`](api_validator.py) | [Browser Validator](https://api-design-tools.github.io/api-design-principles/) | JSON & YAML validation, 32-rule filter |
| REST Naming & Methods | [rest-api-naming-and-http-semantics.md](guides/rest-api-naming-and-http-semantics.md) | [rest-naming-and-methods.html](https://api-design-tools.github.io/api-design-principles/rest-naming-and-methods.html) | `RFC 9110`, `RFC 7396`, `ETag` / `If-Match` |
| Pagination & Filtering | [pagination-filtering-and-sorting.md](guides/pagination-filtering-and-sorting.md) | [pagination-and-filtering.html](https://api-design-tools.github.io/api-design-principles/pagination-and-filtering.html) | Keyset cursors vs `OFFSET`, `OWASP API4` |
| RFC 9457 Error Handling | [error-handling-rfc9457-and-status-codes.md](guides/error-handling-rfc9457-and-status-codes.md) | [error-handling-rfc9457.html](https://api-design-tools.github.io/api-design-principles/error-handling-rfc9457.html) | `application/problem+json`, status matrix |
| Versioning & Rate Limits | [api-versioning-idempotency-and-rate-limiting.md](guides/api-versioning-idempotency-and-rate-limiting.md) | [versioning-idempotency-rate-limits.html](https://api-design-tools.github.io/api-design-principles/versioning-idempotency-rate-limits.html) | `Idempotency-Key`, `Sunset`, `RateLimit-*` |
| REST vs GraphQL vs gRPC | [rest-vs-graphql-vs-grpc-vs-webhooks.md](guides/rest-vs-graphql-vs-grpc-vs-webhooks.md) | [rest-vs-graphql-vs-grpc.html](https://api-design-tools.github.io/api-design-principles/rest-vs-graphql-vs-grpc.html) | Protocol selection and hybrid stacks |
| OWASP API Security Top 10 | [api-security-owasp-checklist.md](guides/api-security-owasp-checklist.md) | [api-security-owasp-checklist.html](https://api-design-tools.github.io/api-design-principles/api-security-owasp-checklist.html) | BOLA/IDOR, ULID IDs, input bounds |
| Webhooks & Async APIs | [webhook-design-and-async-apis.md](guides/webhook-design-and-async-apis.md) | [webhook-design-and-async-apis.html](https://api-design-tools.github.io/api-design-principles/webhook-design-and-async-apis.html) | HMAC-SHA256 signatures, `202` polling |
| AI-Agent & MCP Ready APIs | [ai-agent-ready-api-design.md](guides/ai-agent-ready-api-design.md) | [ai-agent-ready-api-design.html](https://api-design-tools.github.io/api-design-principles/ai-agent-ready-api-design.html) | `operationId`, strict enums, recovery |
| OpenAPI Linter & Diff CLI | [openapi-linter-and-style-guide.md](guides/openapi-linter-and-style-guide.md) | [openapi-linter-and-style-guide.html](https://api-design-tools.github.io/api-design-principles/openapi-linter-and-style-guide.html) | Presets, `--diff`, SARIF 2.1.0 |
| Style Guides Compared | [api-style-guides-compared.md](guides/api-style-guides-compared.md) | [api-style-guides-compared.html](https://api-design-tools.github.io/api-design-principles/api-style-guides-compared.html) | Haufe-Lexware vs Zalando vs Google AIP |

## Frequently asked questions

### What are the most important REST API design principles?
Use plural resource nouns and standard HTTP methods (`RFC 9110`), return `RFC 9457` Problem Details (`application/problem+json`) on `4xx`/`5xx`, enforce bounded cursor pagination on collection `GET` endpoints, accept `Idempotency-Key` headers on `POST` mutations, document `429` with `RateLimit-*` headers, and bound input strings and arrays (`OWASP API4:2023`).

### How does this differ from static style guides like Haufe-Lexware?
Static style guides document rules for human reading. This repository ships both the reference handbook and an automated OpenAPI 3.0/3.1 validator (`api_validator.py`), a browser validator, breaking-change diffing, and a GitHub Action that reports violations directly in Pull Requests.

### Does the OpenAPI validator require Node.js, Docker, or pip packages?
No. `api_validator.py` runs on Python 3.9+ standard library alone for both JSON and YAML OpenAPI specs (and uses `PyYAML` automatically if already installed).

### Why use RFC 9457 instead of RFC 7807?
RFC 9457 (published in 2023) obsoleted RFC 7807. It keeps the `application/problem+json` media type and `type`/`title`/`status`/`detail`/`instance` members while clarifying multiple problem types and extension fields.

### How can a team enforce custom rules across multiple repositories?
Copy [`.api-rules.example.json`](.api-rules.example.json) as `.api-rules.json` (or pick a preset in `presets/`), customize `disabled_rules`, `severity_overrides`, and `allowed_version_prefixes`, and pass `config: .api-rules.json` to `api-design-tools/api-design-principles@v1`.

## Contributing and tests

```bash
python3 -m unittest discover -s tests -v
```

See [`CONTRIBUTING.md`](CONTRIBUTING.md) before opening a Pull Request. Distributed under the **MIT License** ([`LICENSE`](LICENSE)).
