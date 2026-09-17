# Deployment

## Images

`Dockerfile.main` builds one image used by both the API and workers:

- API: `uvicorn main:app --host 0.0.0.0 --port 8011`
- Worker: `taskiq worker --workers 2 --max-async-tasks 50 --ack-type when_received src.taskiq_brokers:items_broker src.items.tasks`

Scale workers per queue independently. One worker container per broker.

## Environment

All keys are listed in `.env.example` and read in `src/core/config.py`.
Minimum for production:

```
TOOL_ENV=prod                # hides /docs
APP_NAME, ROOT_PATH          # ROOT_PATH when mounted under a gateway prefix
DATABASE_URI, DATABASE_NAME  # Mongo replica set for transactions
REDIS_CACHE_URL
NATS_SERVER_HOST, NATS_STREAM_NAME
WEBHOOK_SHARED_SECRET
AWS_ACCESS_KEY / AWS_SECRET_ACCESS_KEY (or IAM role), S3_BUCKET_NAME, S3_BUCKET_REGION
GEMINI_API_KEY / ANTHROPIC_API_KEY / GOOGLE_CLOUD_PROJECT as needed
OTEL_ENABLED=True, OTEL_ENDPOINT, OBS_AUTH_TOKEN
```

## Local stack

`docker-compose.yml` runs api + items_worker + mongo + redis + nats (JetStream enabled).
`make start`, `make stop`, `make clean`, `make logs`.

## Observability

- OTEL traces/metrics/logs export to `OTEL_ENDPOINT` (OTLP/HTTP) with `x-auth-token`.
- New Relic is optional: `newrelic.ini` + `NEW_RELIC_LICENSE_KEY`, run via
  `newrelic-admin run-program uvicorn ...` (commented in `scripts/start_server.sh`).

## AWS Elastic Beanstalk (optional)

`.platform/hooks/postdeploy/01_setup_gcp_wif.sh` writes a GCP Workload Identity
Federation credential file so Vertex AI works from EC2 without a key file.
Replace the `<PLACEHOLDERS>` or delete the directory.

## Health

`GET /health` returns `{"status": "ok", "mongo": "connected"}` or `degraded`.
Point load-balancer checks at it.
