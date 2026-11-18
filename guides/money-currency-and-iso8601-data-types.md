# Money, currencies, and ISO 8601 data types

Back to [API Design Principles](../README.md) | Web version: [money-currency-and-iso8601-data-types.html](https://api-design-tools.github.io/api-design-principles/money-currency-and-iso8601-data-types.html)

Two primitive mistakes cause silent accounting and scheduling bugs in JSON APIs: representing currency with binary floating-point numbers (`ADP-029`) and omitting explicit timezone formats on timestamps (`ADP-022`). Both are checked automatically by `api_validator.py`.

## 1. Integer minor units and ISO 4217 currency (`ADP-029`)

In IEEE 754 floating point, `0.1 + 0.2 === 0.30000000000000004`. Never emit `{ "amount": 19.99 }`. Pair an integer `*_minor` count with a 3-letter uppercase ISO 4217 currency code:

```json
{
  "amount_minor": 1999,
  "currency": "USD"
}
```

Watch the currency exponent when converting minor units for display:

| Currency | ISO 4217 code | Decimal exponent | Example `amount_minor` -> Display |
| :--- | :--- | :--- | :--- |
| US Dollar | `USD` | 2 | `4990` -> `$49.90` |
| Euro | `EUR` | 2 | `4990` -> `€49.90` |
| Japanese Yen | `JPY` | 0 | `5000` -> `¥5000` |
| Bahraini Dinar | `BHD` | 3 | `1500` -> `1.500 BHD` |

For sub-cent FX conversion rates or cryptographic ledger precision (`8` to `18` decimals), encode exact decimal strings such as `"unit_price_decimal": "0.00042500"`, never floats.

## 2. ISO 8601 UTC timestamps and naming consistency (`ADP-022`, `ADP-038`)

Always serialize timestamps in UTC with `Z` offset and annotate every `*_at` property in OpenAPI with `"type": "string", "format": "date-time"`. Pick one casing style (`snake_case` vs `camelCase`) across all JSON properties and PascalCase for `components.schemas` keys (`ADP-038`).
