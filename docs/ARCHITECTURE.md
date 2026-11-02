# Architecture

This document is the team's source of truth for how the product is designed. The style is a **modular monolith with independently scalable background workers and an API-first design**, without microservices.

Each diagram is labelled:
- **Built:** the code in this repo does this today.
- **Target:** the agreed design, not built yet.
- **Partly built:** the status table or a note says which parts exist.

## What exists today

| Layer | Built | Target |
|---|---|---|
| 1. Experience | Streamlit clerk page with trace panel | Next.js web app and admin console |
| 2. Edge and security | CORS limit, file checks, 10 MB cap, rate limiting, Clerk token verification | HTTPS, WAF, sign-in screens, authorization |
| 3. Control plane | Stateless `POST /v1/extract` and `/v1/extract-eml`; organizations, members, roles and audit events | Shipments, jobs, review |
| 4. Data and messaging | Temporary local files, deleted after each request; PostgreSQL schema and migrations, not yet used by the app | App use of PostgreSQL, Redis, job queue, private object storage |
| 5. Document intelligence | All stages, running inside the API process | The same stages in separate workers |
| 6. Observability | OpenTelemetry spans, safe JSON logs, in-memory counters | Collector, Grafana or CloudWatch dashboards |

## Code layers

```text
app/
  main.py            Control plane: HTTP routes
  core/              Platform: settings, errors, telemetry
  ingestion/         Platform: upload checks, storage, .eml attachments
  pipeline/          Document intelligence: OCR, PII, vision, LLM, runner
  domains/meridian/  Meridian only: schemas, prompt, business rules
ui/                  Experience: Streamlit page
```

A new document workflow should add a folder under `domains/`. `pipeline/` still imports Meridian's schemas and rules directly, so that boundary needs an interface before a second domain is added.

## 1. Complete system architecture

**Status: Target.** The status table above shows what exists today.

```mermaid
flowchart TB
    users["Business customers and operators"]

    subgraph L1["1. Experience"]
        web["Enterprise web application"]
        admin["Workspace and admin console"]
    end

    subgraph L2["2. Edge and security"]
        edge["CDN, WAF, HTTPS"]
        auth["Authentication and authorization"]
        limit["Rate limiting"]
        edge --> auth --> limit
    end

    subgraph L3["3. Application control plane: FastAPI"]
        api["REST API"]
        ingest["Document ingestion"]
        tenants["Tenant and user management"]
        audit["Audit events"]
        orchestrator["Shipment workflow orchestrator"]
        results["Results and review management"]
        api --> ingest --> orchestrator
        api --> tenants
        api --> audit
        api --> results
    end

    subgraph L4["4. Data and messaging"]
        redis[("Redis: rate limits")]
        storage[("Private temporary object storage")]
        queue[["Durable job queue"]]
        db[("PostgreSQL: source of truth")]
    end

    subgraph L5["5. Document intelligence workers"]
        validate["File re-validation"]
        render["PDF rendering"]
        ocr["Local OCR"]
        pii["Presidio PII engine"]
        vision["Secure vision fallback"]
        gateway["LLM provider gateway"]
        pydantic["Normalization and Pydantic validation"]
        rules["Deterministic business rules"]
        validate --> render --> ocr --> pii
        pii -->|"OCR readable"| gateway
        pii -->|"OCR poor"| vision
        gateway --> pydantic
        vision --> pydantic
        pydantic --> rules
    end

    subgraph L6["6. Observability"]
        otel["OpenTelemetry collector"]
        traces["Distributed traces"]
        logs["Structured safe logs"]
        metrics["Metrics"]
        otel --> traces
        otel --> logs
        otel --> metrics
    end

    llm["Hosted LLM provider"]

    users --> web
    users --> admin
    web --> edge
    admin --> edge
    limit --> api
    limit -.-> redis
    ingest --> storage
    orchestrator --> db
    orchestrator --> queue
    queue --> validate
    storage --> validate
    gateway -->|"masked text only"| llm
    vision -->|"redacted images only"| llm
    rules --> db
    results --> db
    audit --> db
    api -.-> otel
    L5 -.-> otel
```

## 2. Detailed document-processing architecture

**Status: Partly built.** The steps match the code, except that job creation and saving results are Target.

```mermaid
flowchart TB
    upload["Upload shipment packet"] --> check["Validate file bytes, type and size"]
    check --> job["Create processing job (Target)"]
    job --> render["Render PDF pages"]
    render --> ocr["Run local OCR with word boxes"]
    ocr --> detect["Presidio analyzer and signature band"]
    detect --> tokens["Stable placeholders, in memory only"]
    tokens --> quality{"OCR quality sufficient?"}

    quality -->|"Yes"| masked["Masked text only"]
    masked --> extract["LLM classification and field extraction"]

    quality -->|"No"| safe{"Word boxes found and vision model configured?"}
    safe -->|"Yes"| redact["Paint out flagged boxes, contact lines, receipt band"]
    redact --> vision["Vision call with redacted images only"]
    safe -->|"No"| manual["Manual review required"]

    extract --> normalize["Normalize dates, quantities and weight"]
    vision --> normalize
    normalize --> validate["Pydantic schema validation"]
    validate --> rule["Deterministic rule engine"]
    rule --> persist["Persist safe results (Target)"]

    persist --> cleanup["Delete uploads and clear placeholder map"]
    manual --> cleanup
    cleanup --> result["Return final result and telemetry"]
```

Every path reaches the cleanup step, including failures. Normalization and validation run together inside the Pydantic models.

## 3. Production database architecture

**Status: Partly built.** The tables and migrations exist in `app/db/models.py` and `migrations/`, but the app doesn't read or write them yet.

```mermaid
erDiagram
    ORGANIZATIONS ||--o{ SHIPMENTS : owns
    ORGANIZATIONS ||--o{ AUDIT_EVENTS : records
    ORGANIZATIONS ||--o{ ORGANIZATION_MEMBERS : has
    USERS ||--o{ ORGANIZATION_MEMBERS : joins
    SHIPMENTS ||--o{ DOCUMENTS : contains
    SHIPMENTS ||--o{ PROCESSING_JOBS : triggers
    PROCESSING_JOBS ||--o| VERIFICATION_RESULTS : produces
    DOCUMENTS ||--o{ EXTRACTION_RESULTS : produces
    VERIFICATION_RESULTS ||--o{ REVIEW_ACTIONS : receives

    ORGANIZATIONS {
        uuid id PK
        string name
        string plan
        datetime created_at
    }
    USERS {
        uuid id PK
        string email
        datetime created_at
    }
    ORGANIZATION_MEMBERS {
        uuid organization_id FK
        uuid user_id FK
        string role
    }
    SHIPMENTS {
        uuid id PK
        uuid organization_id FK
        string reference
        string status
    }
    DOCUMENTS {
        uuid id PK
        uuid organization_id FK
        uuid shipment_id FK
        string document_type
        string storage_key
        string processing_status
        int page_count
        datetime deleted_at
    }
    EXTRACTION_RESULTS {
        uuid id PK
        uuid organization_id FK
        uuid document_id FK
        json fields
        string quantity_unit
        float ocr_mean_confidence
        string prompt_version
    }
    PROCESSING_JOBS {
        uuid id PK
        uuid organization_id FK
        uuid shipment_id FK
        string job_status
        string idempotency_key
        int attempts
        string error_class
        json timings_ms
        json entity_counts
    }
    VERIFICATION_RESULTS {
        uuid id PK
        uuid organization_id FK
        uuid job_id FK
        string status
        string reason
    }
    REVIEW_ACTIONS {
        uuid id PK
        uuid organization_id FK
        uuid verification_result_id FK
        uuid reviewer_id FK
        string action
        datetime created_at
    }
    AUDIT_EVENTS {
        uuid id PK
        uuid organization_id FK
        uuid actor_id FK
        string action
        string target
        string request_id
        datetime created_at
    }
```

Rules for this schema:
- Every tenant table carries `organization_id`, and foreign keys between tenant tables include it. PostgreSQL row-level security also limits each signed-in request to one organization.
- No table stores original filenames, OCR text, prompts or the placeholder map.
- Audit events are append-only for signed-in requests, and hold record IDs, never field values.
- `storage_key` is cleared once the file is deleted.

## 4. API architecture

**Status: Target for the job flow.** `POST /v1/extract` stays synchronous, as the assignment requires, and is what exists today. Both flows must share one pipeline.

```mermaid
sequenceDiagram
    actor Customer
    participant Frontend
    participant API as FastAPI
    participant Queue as Job queue
    participant Worker as Processing worker
    participant DB as PostgreSQL

    Customer->>Frontend: Upload documents
    Frontend->>API: Create shipment and submit
    API->>DB: Save processing record
    API->>Queue: Enqueue job (IDs only)
    API-->>Frontend: 202 Accepted and job ID
    Frontend-->>Customer: Processing started
    Queue->>Worker: Deliver job
    Worker->>Worker: OCR, mask, extract, validate
    Worker->>DB: Save results and status
    Frontend->>API: Poll job status
    API->>DB: Read status and results
    API-->>Frontend: Completed response
    Frontend-->>Customer: Show verification results
```

| Endpoint | Status | Purpose |
|---|---|---|
| `POST /v1/extract` | Built | One file or a pair; returns the full result |
| `POST /v1/extract-eml` | Built | Every attachment in an `.eml` file |
| `GET /v1/trace/last` | Built | Sanitized trace of the last request |
| `GET /v1/metrics` | Built | Counters |
| `GET /healthz` | Built | Health check |
| `POST /v1/shipments` | Target | Create a shipment |
| `POST /v1/shipments/{id}/documents` | Target | Add documents |
| `POST /v1/shipments/{id}/jobs` | Target | Start processing; returns 202 |
| `GET /v1/jobs/{id}` | Target | Job status and result |
| `POST /v1/results/{id}/reviews` | Target | Record a human review |
| `/v1/organizations`, `/v1/users`, `/v1/analytics`, `/v1/audit-events` | Target | Administration and reporting |

## 5. Production deployment architecture

**Status: Target.** Nothing is deployed yet.

```mermaid
flowchart TB
    internet["Internet and customers"] --> edge["Route 53, CloudFront, AWS WAF"]
    edge --> frontend["Next.js frontend"]
    edge --> alb["Application Load Balancer"]

    subgraph aws["AWS"]
        sqs[["Amazon SQS and dead-letter queue"]]
        subgraph ecs["ECS Fargate"]
            apis["FastAPI containers"]
            workers["OCR and AI worker containers"]
        end
        rds[("Amazon RDS PostgreSQL")]
        secrets["Secrets Manager and KMS"]
        s3[("Private S3 temporary storage")]
        cache[("ElastiCache Redis")]
    end

    subgraph monitoring["Monitoring"]
        otel["OpenTelemetry"] --> dash["CloudWatch or Grafana"]
    end

    alb --> apis
    apis --> sqs
    sqs --> workers
    apis --> rds
    apis --> secrets
    apis --> s3
    apis --> cache
    workers --> rds
    workers --> secrets
    workers --> s3
    workers -->|"masked content only"| llm["Hosted LLM"]
    apis -.-> otel
    workers -.-> otel
```

## 6. Security architecture

**Status: Partly built.** Masking, the "Safe to send?" residual scan, the fallback rule, output scrubbing, generic errors, token verification and tenant isolation exist. There's no separate gateway component yet, and sign-in screens and network limits are Target.

```mermaid
flowchart TB
    content["Document content"] --> gateway["Privacy gateway"]
    gateway --> detect["PII detection"]
    detect --> mask["Masking and validation"]
    mask --> safe{"Safe to send?"}
    safe -->|"Yes: masking finished and residual scan clean"| request["Approved LLM request"]
    safe -->|"No: fail closed"| reject["Reject or manual review"]
    request --> response["Structured model response"]
    response --> output["Output check, Pydantic validation, rules"]
```

Controls across the system:

| Control | Rule |
|---|---|
| Model calls | Only masked text or redacted images leave the machine |
| Placeholder map | In memory for one request, cleared in `finally` |
| Uploads | Bytes checked, random names, deleted after processing |
| Telemetry | Allow-listed keys only; never text, prompts, values or filenames |
| Client errors | Generic message; the log records only an error class |
| Secrets | Environment variables only; `.env` is never committed |
| Business decision | Deterministic code, never the model |

## Decisions

**Requests switch to a restricted database role (2026-11-02).** PostgreSQL superusers skip row-level security, and the database user in `docker-compose.yml` is one. Each signed-in request therefore runs `SET LOCAL ROLE meridian_app`, so the policies always apply. A deployed app should also connect as a non-superuser.

**Sign-in uses Clerk (2026-11-02).** It's the fastest route to sign-up, sign-in and password reset, and works well with the planned Next.js app. The API only verifies signed tokens with Clerk's public keys, so it holds no passwords. The trade-offs are an outside service holding user emails, and a pricing dependency to review before launch. AWS Cognito was the alternative: it keeps users in our AWS account, but it's slower to set up and harder to test locally.

## Corrections made to the original diagrams

The six diagrams keep their original design, with these fixes:

1. Presidio runs before image redaction, because redaction needs its results.
2. The vision call is the extraction call, so it joins at normalization instead of passing through Presidio and a second model call.
3. Normalization happens with validation, because `"1,200"` fails a plain integer check.
4. Workers save to PostgreSQL only and don't call the results module directly.
5. Workers now read from storage, and PDF rendering appears in the system diagram.
6. Files are validated at the API before a job exists, then re-checked by the worker.
7. Verification results link to a job, so re-runs keep their history.
8. Added `organization_id` on tenant tables, roles, review actions and fields the empty tables lacked.
9. "Safe to send?" now has defined criteria, and model output gets checked.

The manual review path still needs a safe status saved once the database exists, so the exception center has a record to show.
