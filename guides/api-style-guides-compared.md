# API Style Guides Compared: Haufe-Lexware vs Zalando vs Google AIP vs Executable Rules (2026)

Back to [API Design Principles](../README.md) | Web version: [api-style-guides-compared.html](https://api-design-tools.github.io/api-design-principles/api-style-guides-compared.html)

Engineering teams adopting REST standards usually look at three well-known references: Haufe-Lexware API Style Guide, Zalando RESTful API and Event Guidelines, and Google API Improvement Proposals (AIP). Reading a style guide is a good start, yet human code reviewers miss inconsistent error formats, missing `Idempotency-Key` headers, and unbounded arrays under sprint deadlines.

## 1. Feature & enforcement comparison

| Criteria | Haufe-Lexware API Style Guide | Zalando RESTful Guidelines | Google AIP | api-design-tools/api-design-principles |
| :--- | :--- | :--- | :--- | :--- |
| **Primary Format** | Static Markdown docs | Static docs (+ separate Zally server) | Static AIP docs (+ protobuf `api-linter`) | **Practical handbook + zero-dependency OpenAPI linter** |
| **OpenAPI 3.0 / 3.1 CLI** | None | Separate Java/Docker service (Zally) | Protobuf/gRPC focused | **Single Python file (`api_validator.py`), JSON + YAML** |
| **GitHub Action Built-in** | No | No | Custom setup | **Yes (`action.yml` + Step Summary + SARIF)** |
| **Breaking Change Diff** | No | No | `buf` / proto only | **Yes (`--diff base head`)** |
| **Browser Validator** | No | No | No | **Yes (client-side GitHub Pages UI)** |
| **Industry Presets** | Single house style | Single house style | Google Cloud style | **`google-aip`, `stripe-style`, `owasp-api-top10`, `strict-public-api`** |

## 2. How to migrate from static Markdown style guides

1. Pick the preset closest to your architecture (`--preset google-aip` or `--preset stripe-style`).
2. Copy [`.api-rules.example.json`](../.api-rules.example.json) as `.api-rules.json` in your platform repository and list any intentional legacy exceptions in `disabled_rules` or `ignore_paths`.
3. Add `uses: api-design-tools/api-design-principles@v1` with `fail-on: warning` for new services and `fail-on: error` for existing APIs.
4. Review the generated `api-design-report.md` in Pull Requests instead of arguing about casing and status codes in code review comments.
