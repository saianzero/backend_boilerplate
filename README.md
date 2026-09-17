# Backend Boilerplate (FastAPI + Beanie + Taskiq)

Production-shaped starting point for async Python services. Copy it, rename
the `items` module, and build.

**Stack**: FastAPI · MongoDB via Beanie ODM · Redis · Taskiq workers on NATS
JetStream · dependency-injector · OpenTelemetry · S3 · SMTP · LLM fallback
chain (Gemini API → Vertex AI → Claude).

```
main.py                     app factory, lifespan, middleware, router wiring
src/
  core/                     config, DI container, Mongo/Beanie, Redis, singleton
  common/                   shared models, repositories, schemas, services, utils
  items/                    EXAMPLE feature module - copy this to add features
  internal/                 platform webhooks (user deleted, org deleted)
  middleware/               rate limiting, request logging
  observability/            OpenTelemetry bootstrap
  taskiq_brokers.py         NATS brokers, one per queue
  constants.py              static constants
tests/                      hermetic tests (in-memory Mongo), fixtures in conftest.py
docs/                       architecture, how to add a module, LLM, deployment
```

## Quick start

```bash
cp .env.example .env                 # fill in what you need (defaults work locally)
make start                           # api + worker + mongo + redis + nats in docker
open http://localhost:8011/docs
```

Without Docker (needs Mongo, Redis and NATS with JetStream running locally):

```bash
make venv && make install            # uv venv (python 3.12) + requirements-dev.txt
make run                             # uvicorn --reload on :8011
make worker                          # taskiq worker for the items queue
make test
```

`pipenv` users: `pipenv install --dev` reads the `Pipfile` (no lock file is committed).

## Try it

Every request needs the `x-user-data` header the API gateway normally injects:

```bash
H='x-user-data: {"user_id":"u1","org_id":"o1","role":"Admin","email":"a@b.c","name":"Ada"}'

curl -H "$H" -X POST localhost:8011/items/create -H 'content-type: application/json' \
     -d '{"name":"First item","tags":["demo"]}'
curl -H "$H" 'localhost:8011/items/list?page=1&page_size=10&sort_by=name&sort_order=asc'
curl -H "$H" 'localhost:8011/items/search?q=first'
```

File upload flow (browser → S3 direct, then background processing):

```bash
# 1. get PUT urls
curl -H "$H" -X POST localhost:8011/items/generate-presigned-url -H 'content-type: application/json' \
     -d '[{"file_name":"a.pdf","file_type":"application/pdf","file_size":1234}]'
# 2. PUT the bytes to upload_url (client side)
# 3. confirm -> creates Item, queues process_item_task, returns job_id
curl -H "$H" -X POST localhost:8011/items/process-uploaded -H 'content-type: application/json' \
     -d '[{"file_data":{"file_name":"a.pdf","file_type":"application/pdf","file_size":1234},"aws_object_name":"<from step 1>"}]'
# 4. poll
curl -H "$H" localhost:8011/items/job-status/<job_id>
```

## What is where

| Need | Go to |
|---|---|
| Add an env var | `src/core/config.py`, `.env.example` |
| Add a model | `src/<module>/models/*.py` (auto-discovered), inherit `BaseDocument` |
| Generic CRUD / pagination / search | `src/common/repositories/base_repository.py` |
| List endpoint filters + sorting | `src/common/schemas/requests/pagination.py` (`ListRequestBase`) |
| Paginated response envelope | `src/common/schemas/responses/pagination.py` |
| Register service in DI | `src/core/container.py` |
| Wire router | `main.py` (`include_router` + `container.wire`) |
| Auth / current user | `src/common/utils/get_current_user.py`, `role_access_decorator.py` |
| Background task | `src/<module>/tasks.py`, broker in `src/taskiq_brokers.py` |
| Track a batch job in Redis | `src/common/utils/job_tracker.py` |
| Call an LLM with a schema | `src/common/utils/llm_util.py` (`get_default_llm_util()`), prompts in `src/common/prompts.py` |
| S3 presigned URLs / upload / download | `src/common/utils/aws_utils.py` |
| Extract text from PDF/DOCX/PPTX | `src/common/utils/document_utils.py` |
| CSV / Excel ingestion | `src/common/utils/csv_utils.py` |
| Send email | `src/common/repositories/email_repository.py`, template in `src/constants.py` |
| Reusable HTTP errors | `src/common/repositories/error_repository.py` |
| Platform webhooks (user/org deleted) | `src/internal/router.py` (`OWNED_MODELS`) |
| Rate limits | `src/middleware/rate_limiting.py`, `RATE_LIMIT_DEFAULT` |
| Tracing / metrics / logs | `src/observability/bootstrap.py`, `OTEL_ENABLED` |
| Test fixtures | `tests/conftest.py` |

Every file carries a module docstring with usage examples. Start with
`docs/ARCHITECTURE.md`, then `docs/ADDING_A_MODULE.md`.

## Example module: `items`

| Method | Path | Notes |
|---|---|---|
| POST | `/items/create` | JSON create |
| POST | `/items/generate-presigned-url` | upload step 1 |
| POST | `/items/process-uploaded` | upload step 2, queues tasks, returns `job_id` |
| POST | `/items/reprocess` | re-run task for ids |
| GET | `/items/job-status/{job_id}` | Redis-backed batch progress |
| GET | `/items/list` | pagination, filters, sorting via query params |
| GET | `/items/search?q=` | regex search across fields |
| GET | `/items/stats` | aggregation example |
| GET | `/items/get/{id}` | detail + presigned file url |
| PUT | `/items/update/{id}` | partial update |
| DELETE | `/items/delete/{id}` | guards originals with duplicates |
| POST | `/items/bulk-delete` | admin-only (role gate example) |

Also: `GET /get-user`, `GET /global-search`, `GET /get-username-by-search`,
`POST /internal/user-deleted`, `POST /internal/org-deleted`, `GET /health`.

## Conventions

- **Layers**: router (HTTP) → service (rules, auth, orchestration) → repository (Mongo only). Utils are stateless helpers.
- **Tenancy**: every document has `org_id` + `uploaded_by`; every service method takes `CurrentUser` and scopes by `user.org_id`.
- **Errors**: services raise `HTTPException`; repositories never do.
- **Tasks**: thin `@broker.task` wrapper + private `_do_work()`; track progress with `JobTracker`.
- **LLM**: always pass a pydantic `structure`; never parse JSON by hand.
- **Config**: only `src/core/config.py` reads the environment.
- **Formatting & lint**: `ruff` (`make lint`); pre-commit runs ruff, mypy, bandit, detect-secrets.

## Tests

```bash
make test        # 25 tests, no external services (mongomock-motor)
```

Repository tests hit an in-memory Mongo, service tests mock AWS and the queue,
router tests override the service through the DI container. See
`tests/conftest.py`.

## Deployment

`Dockerfile.main` builds a slim image (`uvicorn main:app` for the API, `taskiq
worker ...` for workers). See `docs/DEPLOYMENT.md` for env, scaling and the
optional Elastic Beanstalk / GCP Workload Identity hook.
