# GraphQL API design principles and security controls

Back to [API Design Principles](../README.md) | Web version: [graphql-api-design-principles.html](https://api-design-tools.github.io/api-design-principles/graphql-api-design-principles.html)

GraphQL fits multi-entity UI aggregators and mobile backends where a single screen pulls nested data across several services (`ADP-031`). Because HTTP caches and URL firewalls cannot inspect GraphQL selection sets by path alone, public GraphQL endpoints need strict query budgets and schema discipline (`ADP-041`).

## 1. Relay cursor connections instead of offset lists

Never expose raw unbounded lists like `orders(offset: Int, limit: Int): [Order!]!`. Use cursor connections with bounded `first` arguments so clients traverse ordered sets in constant database time (`ADP-010`):

```graphql
type Query {
  orders(first: Int = 25, after: String): OrderConnection!
}

type OrderConnection {
  edges: [OrderEdge!]!
  pageInfo: PageInfo!
}
```

Reject any request where `first > 100` in the resolver or validation directive before running the query.

## 2. Query depth, cost budgets, and persisted queries (`ADP-041`)

An attacker can turn recursive relationships into an exponential database fan-out with a 15-line query. Enforce three controls before execution:

| Defense | Threshold | Why it matters |
| :--- | :--- | :--- |
| Max query depth | 8 to 10 levels | Stops cyclic traversal such as `user.orders.user.orders` |
| Complexity cost cap | Per-field multiplier on lists | Bounds `orders(first: 100) { items(first: 100) }` multiplication |
| Persisted operations | SHA-256 query allowlist in production | Eliminates ad-hoc arbitrary AST parsing on public APIs |
| Introspection guard | Disabled on public unauthenticated traffic | Hides internal type graph structure from automated scanners |

## 3. Typed union errors instead of top-level null ambiguity

Keep transport failures (`401`, `429`, `503`) at the HTTP layer, and model domain validation or state conflicts inside mutation return unions so typed clients handle failures explicitly:

```graphql
union CancelOrderResult = OrderCancelled | OrderAlreadyShipped | ValidationProblem

type OrderAlreadyShipped {
  code: String!
  shippedAt: DateTime!
}
```

Batch leaf lookups with per-request DataLoader instances to prevent N+1 database queries across list fields.
