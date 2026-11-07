# Mailbox intake

An organization can email a document packet to its own address, and the documents are checked with no manual upload. Each accepted email becomes one shipment, named like `EMAIL-20261107-3F9A2C`, with one check.

**Status:** built and tested, but **no email provider is connected**. So no real email reaches it yet, and `POST /v1/inbound/email` refuses everything until `INBOUND_EMAIL_SECRET` and `INBOUND_EMAIL_DOMAIN` are set.

## How it works

1. An admin lists the allowed senders on **Settings → Mailbox**, either full addresses or domains, and gets an address like `inbox+<24 hex characters>@in.example.com`.
2. The email provider receives mail for that domain and posts the raw message to `POST /v1/inbound/email`, signed with the shared secret.
3. The API checks, in order:
   - the signature and its timestamp, which must be within 5 minutes, so a captured request can't be replayed
   - that exactly one recipient is an address at the configured domain
   - that the address belongs to a mailbox that's turned on
   - that the sender is on that mailbox's list
   - that at least one attachment is a PDF, PNG or JPEG by its bytes, up to the usual size limit and 10 attachments
   - the organization's monthly plan limit
4. It stores the attachments under random names, creates the shipment, and starts the check. Webhooks fire when it finishes, as for any job.

Rejected mail gets a 200 with `{"accepted": false, "reason": "..."}`, so the provider doesn't keep retrying. Logs and audit events record the reason only, never an address. **Replace address** on Settings issues a new address and turns off the old one at once.

## Connecting a provider

Any provider that can forward the raw message (MIME) to a web address works, but most need a small adapter to add our signature. `scripts/send_inbound_email.py` shows the signing:

```
X-Meridian-Inbound-Signature: t=<unix seconds>,v1=<hex HMAC-SHA256 of "<t>.<raw message>" with INBOUND_EMAIL_SECRET>
```

Examples: Cloudflare Email Routing with an Email Worker, Amazon SES receiving rules to a Lambda function, or Postmark or Mailgun inbound routes through a small function. Point the domain's MX records at the provider, then set both variables on the API.

## Limits to know

- **The From address can be forged.** The sender list stops casual misuse, but a spoofed From header passes it. Have the adapter forward only mail that passes SPF, DKIM or DMARC, which every provider above reports.
- **Shipment names don't use the invoice number.** Each email gets a new `EMAIL-` shipment. Renaming or merging is manual, and grouping by reference is only in Intake.
- **The address is in the database as is.** It isn't a password. The sender list and the signature are what protect it, and replacing the address is quick.

## Try it locally

```bash
INBOUND_EMAIL_SECRET=dev-secret INBOUND_EMAIL_DOMAIN=in.localhost uvicorn app.main:app --port 8000
INBOUND_EMAIL_SECRET=dev-secret python scripts/send_inbound_email.py samples/packet_S02_match.eml --to inbox+<token>@in.localhost --from <allowed sender>
```
