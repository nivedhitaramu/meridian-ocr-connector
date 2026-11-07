# Customer API

Connect another system to Meridian: submit a shipment with an API key, then receive a signed webhook when its check finishes. Interactive reference: `/docs` on the API.

Use synthetic documents until the product is cleared for real data.

## API keys

An admin creates keys in the website under **API access**, or with `POST /v1/api-keys`. Each key is shown once, and only a hash is stored. Send it as a header:

```bash
curl -H "X-API-Key: mk_..." https://your-api/v1/shipments
```

- A key acts for its organization with clerk permissions. It can't manage members, keys, webhooks or approvals.
- Each key can make 120 requests a minute by default, and further requests get a 429.
- `POST /v1/api-keys/{id}/rotate` replaces a key. The old one stops working at once.
- `DELETE /v1/api-keys/{id}` revokes a key.
- Removing the person who created a key stops that key.

## Submit a shipment

| Step | Request |
|---|---|
| 1. Create | `POST /v1/shipments` with `{"reference": "MF-1001"}` |
| 2. Upload | `POST /v1/shipments/{id}/documents` with a multipart `file`, once per document |
| 3. Start | `POST /v1/shipments/{id}/jobs`, with an `Idempotency-Key` header so a retry can't start a second job |
| 4. Read | `GET /v1/jobs/{id}` for the status and saved results |

## Plan limits

Each organization's plan sets a monthly document limit. Starting a check that would pass it returns 402, and nothing is processed. Every finished job counts its documents, including failed and manual-review ones, because the documents were read. `GET /v1/usage` shows this month's totals to supervisors and admins.

| Plan | Documents a month |
|---|---|
| trial | 100 |
| team | 2,000 |
| business | 20,000 |
| enterprise | No limit |

Billing isn't built yet, so staff change an organization's plan.

## Webhooks

Add an endpoint with `POST /v1/webhooks` and `{"url": "https://..."}`. The signing secret is shown once. The address must be public HTTPS.

When a job finishes, each endpoint gets one event:

```json
{
  "event": "job.finished",
  "delivery_id": "...",
  "job_id": "...",
  "shipment_id": "...",
  "reference": "MF-1001",
  "job_status": "succeeded",
  "check_status": "Match",
  "reason": "Invoice quantity equals packing-list quantity (120 cartons)."
}
```

Events carry no extracted field values. Fetch those with `GET /v1/jobs/{id}`.

### Check the signature

Every request has `X-Meridian-Signature: t=<unix time>,v1=<hex>`. `v1` is an HMAC-SHA256 of `<t>.<raw body>`, using your secret. Refuse an old `t`, so a captured request can't be replayed. `verify()` in [`scripts/customer_example.py`](../scripts/customer_example.py) does both, and that script runs the whole flow.

### Retries

Any 2xx response counts as delivered. Anything else is retried up to 5 attempts in total, waiting 30 seconds and then doubling. Redirects aren't followed. A retry keeps the same `X-Meridian-Delivery` ID, so ignore an ID you've already handled. Recent attempts are at `GET /v1/webhooks/deliveries`.
