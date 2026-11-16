# OpenAPI Linter, Breaking-Change Diff & GitHub Action Guide (2026)

Back to [API Design Principles](../README.md) | Web version: [openapi-linter-and-style-guide.html](https://api-design-tools.github.io/api-design-principles/openapi-linter-and-style-guide.html)

`api_validator.py` is a zero-dependency OpenAPI 3.0 and 3.1 linter written in standard library Python 3.9+. It validates JSON and YAML specs locally or inside GitHub Actions without requiring Node.js, npm, or Docker.

## 1. CLI workflows

```bash
# Lint JSON or YAML specs using a built-in industry preset
python3 api_validator.py --spec examples/orders-api-good.openapi.yaml --preset stripe-style

# Lint multiple service specs across a monorepo and write a Markdown report
python3 api_validator.py --spec "services/*/openapi.*" --format markdown --output reports/api-lint.md

# Detect breaking contract changes between main and a feature branch spec
python3 api_validator.py --diff openapi.base.json openapi.head.json --format markdown

# Export SARIF 2.1.0 for GitHub Code Scanning / Security tab
python3 api_validator.py --spec openapi.json --format sarif --output api-lint.sarif
```

## 2. Built-in rule presets (`presets/`)

| Preset (`--preset`) | Focus | Key Overrides |
| :--- | :--- | :--- |
| `google-aip` | URI & resource consistency | Promotes `ADP-002` (kebab-case), `ADP-011` (cursor pagination), `ADP-017` (`operationId`) to `error` |
| `stripe-style` | Payments & developer UX | Promotes `ADP-012` (`Idempotency-Key`), `ADP-013` (`429`), `ADP-019` (examples) to `error` |
| `owasp-api-top10` | Security-only gate | Enforces HTTPS (`ADP-014`), auth (`ADP-015`/`016`), pagination (`ADP-010`), bounded inputs (`ADP-021`) |
| `strict-public-api` | Public SaaS / release gate | Fails on warnings (`fail_on: warning`) and promotes naming/docs checks to `error` |

## 3. GitHub Action with SARIF upload & PR diff

```yaml
- name: Run API Design Principles Validator
  uses: api-design-tools/api-design-principles@v1
  with:
    spec: openapi/orders.yaml
    preset: stripe-style
    diff-base: openapi/orders.base.yaml
    report-format: sarif
    output-file: api-design.sarif

- name: Upload SARIF to GitHub Security
  if: always()
  uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: api-design.sarif
```
