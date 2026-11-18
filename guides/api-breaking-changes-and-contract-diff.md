# API breaking changes and contract diff in CI

Back to [API Design Principles](../README.md) | Web version: [api-breaking-changes-and-contract-diff.html](https://api-design-tools.github.io/api-design-principles/api-breaking-changes-and-contract-diff.html)

Minor API releases must remain backward-compatible (`ADP-027`). Typed SDKs generated from OpenAPI (TypeScript, Go, Swift, Kotlin, Pydantic) break compilation or fail JSON decoding immediately when a server mutates an existing contract without bumping the major version (`/v2`).

## 1. Breaking vs non-breaking classification (`--diff`)

The built-in diff checker (`python3 api_validator.py --diff base.json head.json`) classifies structural changes automatically:

| Contract change | Severity | Why clients break |
| :--- | :--- | :--- |
| Remove path or HTTP method | Breaking | Existing client calls fail with `404`/`405` |
| Add required parameter or make optional parameter required | Breaking | Old requests omit the field and get `400`/`422` |
| Make optional response field optional-to-removed or change type | Breaking | Strongly typed JSON unmarshalers crash on mismatched primitives |
| Shrink parameter or request `enum` values | Breaking | Previously valid request arguments start failing validation |
| Add a new optional query param or optional response field | Non-breaking | Tolerant readers ignore unknown keys safely |
| Add a new endpoint path or new optional HTTP method | Non-breaking | Existing consumers are unaffected |

## 2. Automating contract diff in pull requests

Compare the pull request specification against `main` in GitHub Actions so accidental contract breaks block merge:

```bash
git show origin/main:openapi.json > /tmp/base.openapi.json
python3 api_validator.py --diff /tmp/base.openapi.json openapi.json --format markdown
```

Use `--fail-on none` only when inspecting informational diff output; keep default exit code `1` in release pipelines so breaking changes move into a new `/v2` prefix (`ADP-004`).
