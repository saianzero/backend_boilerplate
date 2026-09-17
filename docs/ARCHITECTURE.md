# Architecture

## Request path

```
client ──(x-user-data)──▶ FastAPI router ──▶ Service ──▶ Repository ──▶ MongoDB (Beanie)
                              │                 │
                              │                 ├──▶ AwsUtil / DocumentUtil / EmailRepository / LLMUtil
                              │                 └──▶ task.kiq() ──▶ NATS JetStream ──▶ Taskiq worker
                              └── get_current_user, access_roles, rate limiter, CORS, HSTS
```

1. **Gateway** authenticates and forwards claims in the `x-user-data` JSON header.
   `get_current_user` turns it into `CurrentUser`. This service must sit behind the gateway.
2. **Router** (`src/<module>/router.py`) declares paths, validates input with pydantic
   schemas, resolves the user, and pulls a service from the DI container.
3. **Service** applies rules: ownership checks (`org_id`), validation that needs data,
   orchestration of utils, dispatch of background tasks, `HTTPException`s.
4. **Repository** is Mongo-only. `BaseRepository` supplies CRUD, paginated lists,
   counts, regex search, `$set` updates and bulk deletes; subclasses add model-specific queries.
5. **Models** are Beanie documents extending `BaseDocument` (timestamps). They are
   auto-discovered by `Database.connect()` from any `src/*/models/` directory.

## Dependency injection

`src/core/container.py` declares one provider per repository/util/service.
Routers use `@inject` + `Depends(Provide[Container.x])`. Services get their
collaborators via constructor args, which makes unit tests plain constructor calls.
Modules that use `Provide[...]` must be listed in `container.wire(modules=[...])` in `main.py`.

## Background work

- `src/taskiq_brokers.py` creates one `PullBasedJetStreamBroker` per queue
  (subject `<NATS_STREAM_NAME>.<id>`). Add ids to `SUBJECT_IDS`.
- Tasks live in `src/<module>/tasks.py`. Services call `task.kiq(...)`.
- Workers run `taskiq worker src.taskiq_brokers:<broker> src.<module>.tasks`; the
  startup hook connects Beanie so tasks use repositories like request code does.
- `JobTracker` (Redis hashes, 24h TTL) tracks a batch: `create` → `mark(queued)` →
  task body inside `async with JobTracker.run(job_id, key)` → `get()` for the status endpoint.

## Storage and files

- Uploads go browser → S3 with presigned PUT urls (`AwsUtil.generate_presigned_put_url`),
  then the client confirms and the server creates the document + queues processing.
  This keeps large bodies off the API.
- Workers download with `download_file_from_s3`, extract text with `DocumentUtil`,
  and delete the temp file in `finally`.
- Duplicate detection: size window (±1 KB) then md5 (`FileService.detect_duplicate`,
  same logic in `items/tasks.py`).

## LLM layer

`LLMUtil` wraps Gemini API → Vertex AI → Claude with automatic fallback on provider
errors, refusals, rate limits and the Vertex daily cap. Callers pass a pydantic
`structure` and get a validated instance back. See `docs/LLM.md`.

## Cross-cutting

- **Logging**: JSON lines to stdout (`setup_logger()`), OTEL trace ids injected when enabled.
- **Observability**: `init_observability(app)` sets traces/metrics/logs exporters (OTLP/HTTP),
  instruments FastAPI, httpx and Taskiq. Off unless `OTEL_ENABLED=True`.
- **Rate limiting**: slowapi, per user per endpoint, default from `RATE_LIMIT_DEFAULT`.
- **Internal webhooks**: `/internal/user-deleted` re-assigns ownership,
  `/internal/org-deleted` purges data, both HMAC-signed. Register models in `OWNED_MODELS`.
- **Multi-tenancy**: `org_id` on every document, every query, every index.

## Lifecycle

`main.lifespan`: Mongo connect → brokers startup → serve → brokers shutdown → Mongo close → Redis close.
