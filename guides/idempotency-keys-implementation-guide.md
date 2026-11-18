# Idempotency keys implementation guide

Back to [API Design Principles](../README.md) | Web version: [idempotency-keys-implementation-guide.html](https://api-design-tools.github.io/api-design-principles/idempotency-keys-implementation-guide.html)

Network timeouts happen after the server commits a charge or inserts an order (`ADP-012`). Clients that retry `POST` requests without an idempotency key create duplicate charges, duplicate shipments, and skewed ledger balances.

## 1. HTTP contract and response codes

Require an `Idempotency-Key` header (UUIDv4 or UUIDv7, max 64 characters) on every non-idempotent state creation endpoint (`POST`). Store a tuple of `(tenant_id, idempotency_key, request_sha256, status, response_status, response_body, expires_at)`.

```http
POST /v1/orders HTTP/1.1
Authorization: Bearer eyJ...
Idempotency-Key: 0193368a-5e2b-7c10-9f41-8a92c110f302
Content-Type: application/json
```

How the server handles each state:

| Request state | HTTP response | Server behavior |
| :--- | :--- | :--- |
| First sighting (key inserted) | Run handler, store `201` + body, return `201 Created` | Commit idempotency record atomically with business transaction |
| Duplicate with identical hash (completed) | Cached `201 Created` + original body + `Idempotent-Replayed: true` | Skip business side effects completely |
| Duplicate while original is in flight | `409 Conflict` (`application/problem+json`) | Tell caller to retry with backoff once first request finishes |
| Same key reused with different payload | `422 Unprocessable Content` | Reject accidental key reuse to keep ledger records consistent |

## 2. Database pattern that avoids race conditions

Acquiring an application mutex in memory fails across multiple API pods. Insert the idempotency row with `ON CONFLICT DO NOTHING` in PostgreSQL before mutating state:

```sql
INSERT INTO idempotency_records (tenant_id, idempotency_key, request_hash, state, expires_at)
VALUES ($1, $2, $3, 'in_progress', NOW() + INTERVAL '24 hours')
ON CONFLICT (tenant_id, idempotency_key) DO NOTHING;
```

If zero rows are inserted, read the existing row. Compare `request_hash`; return `422` on mismatch, `409` if `state = 'in_progress'`, or replay the saved JSON response if `state = 'completed'`. Retain keys for at least 24 hours and purge expired rows with a partitioned table drop or indexed cleanup job.
