# AWS infrastructure

Terraform for staging and production, covering issues #32 (provisioning), #33 (networking and secrets), #34 (deployment pipeline) and #35 (monitoring). **None of it has been applied.** Applying it needs an AWS account, a domain and money, which only the project owner can provide. CI checks that it's valid Terraform.

## What it creates

```
Visitor → CloudFront + WAF → load balancer (HTTPS only, CloudFront only) → website (Next.js) or API (FastAPI)
                                                                              ↓
                                     PostgreSQL (RDS) · Redis (ElastiCache) · S3 uploads · Secrets Manager · KMS
                                                                              ↑
                                       pipeline workers (Celery) ── egress firewall ── model provider only
                                       delivery worker (webhooks, connectors, nightly jobs) ── customers' HTTPS endpoints
```

| Issue | Where |
|---|---|
| ECS Fargate, RDS, ElastiCache, S3, Secrets Manager, KMS | `ecs.tf`, `data.tf` |
| Route 53, CloudFront, WAF, load balancer | `edge.tf` |
| Separate staging and production | `envs/*.tfvars` and `envs/*.backend.hcl`, each with its own state and network |
| Private subnets, egress only to the model provider | `network.tf`, `egress.tf`, `security.tf` |
| Least-privilege IAM, encryption, HTTPS only | `ecs.tf` (roles), `data.tf` (KMS everywhere, TLS-only bucket, `rds.force_ssl`) |
| Deploy pipeline, migrations, secret scanning | `.github/workflows/deploy.yml`, `.github/workflows/ci.yml` |
| Monitoring and alerts | `monitoring.tf`, `scripts/check_log_leaks.py` |

## Decisions

**Celery with Redis stays, instead of SQS (#32 asked for a re-evaluation).**
- The code already relies on Celery's Redis behaviour, and CI tests it: a killed worker's job is delivered again and finishes once.
- Job state and retries live in PostgreSQL, so a dead-letter queue would duplicate what the `failed` and `manual_review` statuses already record.
- Moving to SQS means a new broker and its own redelivery testing, for no gain at this size.
- Revisit if job volume needs more than one Redis node can hold.

**Deliveries run as a separate worker.**
- Webhooks and connectors must reach customers' own addresses, so their worker skips the model-only firewall.
- The app still refuses private and internal addresses (`app/core/webhook_url.py`).
- Pipeline workers, which see document text, can reach only the model provider and Clerk's keys.

**Secrets never enter Terraform state.** Terraform creates each secret empty, and someone puts the value in once with the AWS CLI. The database password is the only exception: Terraform generates it, so it's in state, which is why the state bucket must be encrypted and private.

**The egress firewall can be off in staging.** AWS Network Firewall costs about USD 290 a month per zone. Staging keeps the private subnets and HTTPS-only security groups, but not the domain allow-list.

## Monthly cost estimate (before provisioning)

These are rough figures from AWS's public on-demand prices in USD, for ap-south-1. They exclude tax, data transfer beyond a small amount, and the model provider. **Check them in the AWS Pricing Calculator before applying**, because prices change and I couldn't confirm current ones here.

| Item | Staging | Production |
|---|---|---|
| Fargate: API, workers, delivery, website | ~70 | ~230 (2 of each) |
| RDS PostgreSQL | ~15 (t4g.micro) | ~70 (t4g.small, Multi-AZ) |
| ElastiCache Redis | ~12 | ~50 (2 nodes) |
| NAT gateways (2) | ~70 | ~70 |
| Network Firewall (2 zones) | off | ~580 |
| Load balancer | ~20 | ~25 |
| CloudFront, WAF, Route 53 | ~15 | ~25 |
| VPC interface endpoints (7 × 2 zones) | ~100 | ~100 |
| KMS, Secrets Manager, CloudWatch, ECR, S3 | ~15 | ~30 |
| **Total, roughly** | **~320** | **~1,180** |

The biggest levers are the Network Firewall, NAT gateways and interface endpoints. A single-zone staging setup with fewer endpoints would cost about half.

## First-time setup

1. Create the state bucket and lock table, then fill in the names in `envs/*.backend.hcl`.
2. Fill in `envs/*.tfvars`: the domain, the hosted zone, the alert email and the Clerk issuer.
3. Run `terraform init -backend-config=envs/staging.backend.hcl`, then `terraform apply -var-file=envs/staging.tfvars`.
4. Put values into the secrets listed in the `secrets_to_fill` output.
5. Set the GitHub variables and roles that `.github/workflows/deploy.yml` lists, then merge to `main`.

## Checks still to do after applying

- **#33's "done when":** the deploy workflow's last step tries to reach a host that isn't on the allow-list from a pipeline worker, and fails the deploy if that works.
- **#35's "done when":** force a failure to confirm an alarm email arrives, and run `scripts/check_log_leaks.py` after a seeded test document to confirm no personal data reached the logs.
