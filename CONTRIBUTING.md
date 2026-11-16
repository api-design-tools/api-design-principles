# Contributing to API Design Principles & OpenAPI Validator

Thank you for helping keep API Design Principles (`api-design-principles`) practical, standards-backed, and enforceable in CI/CD.

## How to propose or update a rule

1. Ground every rule in a standard or real production failure:
   - Cite the relevant specification (such as `RFC 9110`, `RFC 9457`, `RFC 8594`, `OWASP API Security Top 10`, `OpenAPI 3.1`, or `Google AIP`).
   - Provide clear `bad_example` and `good_example` HTTP/OpenAPI snippets.

2. Update `rules.json` and `api_validator.py` (if automatable):
   - Add the rule entry to `rules.json` with a unique `ADP-XXX` ID, category, severity (`error`, `warning`, or `info`), and `last_verified` date.
   - If the rule can be checked automatically against OpenAPI 3.0/3.1 specs, implement the check in `api_validator.py` and add unit tests in `tests/test_validator.py`.

3. Run the validator and test suite locally:
   ```bash
   python3 api_validator.py --spec examples/orders-api-good.openapi.json --fail-on error
   python3 api_validator.py --spec examples/orders-api-bad.openapi.json --format markdown
   python3 -m unittest discover -s tests -v
   ```

4. Open a Pull Request:
   - Summarize the rule rationale, false-positive edge cases, and expected violation message in your PR description.
