# OAuth 2.1, PKCE, JWTs, and API keys

Back to [API Design Principles](../README.md) | Web version: [oauth2-pkce-jwt-and-api-keys.html](https://api-design-tools.github.io/api-design-principles/oauth2-pkce-jwt-and-api-keys.html)

Authentication proves caller identity, never tenant ownership (`ADP-015`, `ADP-023`). Modern APIs separate user-delegated OAuth 2.1 tokens (`ADP-043`) from machine-to-machine client credentials and developer API keys, while blocking credentials in query strings (`ADP-016`).

## 1. OAuth 2.1 Authorization Code + PKCE (`ADP-043`)

For browser SPAs, mobile apps, and CLI tools acting for a user, use Authorization Code flow with `S256` PKCE (RFC 9700). Retire implicit flow (`response_type=token`) and password grant (`grant_type=password`).

| Token property | Recommended value | Security reason |
| :--- | :--- | :--- |
| Access token TTL | 5 to 15 minutes | Bounds impact if a stateless JWT leaks before expiration |
| Refresh token behavior | Single-use rotation + reuse detection | Revokes the token family immediately on stolen replay |
| Signing keys | Asymmetric EdDSA or RS256 via `/.well-known/jwks.json` | Gateways verify signatures locally and rotate by `kid` without downtime |
| Audience & scopes | Strict `aud` check + granular `orders:read`, `orders:write` | Prevents tokens issued for billing from calling admin services |

## 2. Server-to-server API keys

When developers integrate scripts or backends without interactive login:

1. Generate high-entropy keys with a recognizable prefix and secret scanner pattern, such as `sk_live_...` or `pk_test_...`.
2. Store only a salted SHA-256 (or HMAC) hash in your database alongside a short non-secret display prefix (`sk_live_4a9f`).
3. Bind every key to an explicit scope set and optional expiration date; reject any API key transmitted in URL query strings (`?api_key=...`, enforced by `ADP-016`).
4. Support two active keys per integration during rotation so callers can switch secrets zero-downtime.
