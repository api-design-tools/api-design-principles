# Webhook Design & Async API Patterns (2026)

Back to [API Design Principles](../README.md) | Web version: [webhook-design-and-async-apis.html](https://api-design-tools.github.io/api-design-principles/webhook-design-and-async-apis.html)

Long-running HTTP requests time out behind load balancers, and unsigned webhook callbacks invite spoofed billing events. Rules `ADP-025` and `ADP-026` cover reliable asynchronous APIs.

## 1. Signed webhooks with replay protection (`ADP-025`)

Follow the Standard Webhooks headers (`Webhook-Id`, `Webhook-Timestamp`, `Webhook-Signature`) so receivers can verify authenticity and reject replayed payloads:

```http
POST https://consumer.example.com/webhooks/orders HTTP/1.1
Content-Type: application/json
Webhook-Id: msg_01J9Z9P3K2M4
Webhook-Timestamp: 1763290000
Webhook-Signature: v1,g0hM9SsE+OTPJTGt/tmIKtSyZlE3uFJELVlNIOLJ1OE=

{
  "id": "evt_01J9Z9P3K2M4",
  "type": "order.paid",
  "created_at": "2026-11-16T10:46:40Z",
  "data": { "order_id": "ord_01J9Z4K8M2P7X3Q9W5V" }
}
```

Verification rules for consumers and senders:
1. Sign `<webhook-id>.<webhook-timestamp>.<raw-body>` using HMAC-SHA256.
2. Compare signatures in constant time (`hmac.compare_digest` in Python, `crypto.timingSafeEqual` in Node.js).
3. Reject timestamps older than 5 minutes to block replay attacks.
4. Deduplicate events by `Webhook-Id` because retries with exponential backoff mean at-least-once delivery.

## 2. Long-running operations with `202 Accepted` (`ADP-026`)

If an export, report, or batch import can take longer than 10 seconds, return `202 Accepted` immediately with a polling URL:

```http
HTTP/1.1 202 Accepted
Location: /v1/jobs/job_01J9Z9T4
Retry-After: 5
Content-Type: application/json

{
  "id": "job_01J9Z9T4",
  "status": "queued",
  "status_url": "https://api.example.com/v1/jobs/job_01J9Z9T4"
}
```

Once the background worker finishes, `GET /v1/jobs/job_01J9Z9T4` returns `status: "completed"` and a `result_url` (or `error` formatted as RFC 9457 Problem Details if it failed).
