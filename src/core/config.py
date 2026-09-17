"""
Central configuration.

Every environment variable the service reads lives here. Nothing else in the
codebase should call ``os.getenv`` / ``decouple.config`` directly; import the
constant from this module instead so the full list of knobs stays in one place.

Rules
-----
- Values that the app cannot run without have **no default** (they raise at
  import time if missing). Everything else has a sane local-dev default.
- ``cast=`` converts strings from the environment (``bool``, ``int``).
- Keep secrets out of git: copy ``.env.example`` to ``.env`` and fill it in.

Example
-------
    from src.core.config import DATABASE_URI, TOOL_ENV

    if TOOL_ENV == "prod":
        ...
"""

from decouple import Csv, config
from dotenv import load_dotenv

# Load ``.env`` into the process environment so ``decouple`` can see it.
load_dotenv()

# --------------------------------------------------------------------------- #
# Application identity
# --------------------------------------------------------------------------- #
APP_NAME = config("APP_NAME", default="backend-service")
# Mounted path prefix when behind a gateway/ingress (e.g. "/api" or "/backend").
ROOT_PATH = config("ROOT_PATH", default="")
# "dev" | "staging" | "prod". Swagger UI is disabled when "prod".
TOOL_ENV = config("TOOL_ENV", default="dev")
# Comma-separated list, e.g. "http://localhost:3000,https://app.example.com".
BACKEND_CORS_ORIGINS = config("BACKEND_CORS_ORIGINS", default="", cast=Csv())
FRONTEND_URL = config("FRONTEND_URL", default="http://localhost:3000")

# --------------------------------------------------------------------------- #
# Datastores
# --------------------------------------------------------------------------- #
DATABASE_URI = config("DATABASE_URI", default="mongodb://localhost:27017")
DATABASE_NAME = config("DATABASE_NAME", default=APP_NAME.replace("-", "_"))
REDIS_CACHE_URL = config("REDIS_CACHE_URL", default="redis://localhost:6379/0")

# --------------------------------------------------------------------------- #
# Task queue (Taskiq + NATS JetStream)
# --------------------------------------------------------------------------- #
NATS_SERVER_HOST = config("NATS_SERVER_HOST", default="localhost:4222")
# One JetStream stream per service; subjects are "<STREAM>.<subject_id>".
NATS_STREAM_NAME = config("NATS_STREAM_NAME", default="BACKEND_JS1")

# --------------------------------------------------------------------------- #
# Auth / identity platform
# --------------------------------------------------------------------------- #
# Upstream identity service used to look up users/orgs by id (see
# ``src/common/utils/auth_identity_client.py``).
AUTH_SERVICE_URL = config("AUTH_SERVICE_URL", default="http://localhost:8001")
# Shared HMAC secret for inbound platform webhooks (``src/internal/router.py``).
WEBHOOK_SHARED_SECRET = config("WEBHOOK_SHARED_SECRET", default="")
# Org id that owns platform-wide resources (optional).
PLATFORM_ORG_ID = config("PLATFORM_ORG_ID", default="")

# --------------------------------------------------------------------------- #
# Object storage (S3-compatible)
# --------------------------------------------------------------------------- #
AWS_ACCESS_KEY = config("AWS_ACCESS_KEY", default="")
AWS_SECRET_ACCESS_KEY = config("AWS_SECRET_ACCESS_KEY", default="")
S3_BUCKET_NAME = config("S3_BUCKET_NAME", default="my-bucket")
S3_BUCKET_REGION = config("S3_BUCKET_REGION", default="ap-south-1")
PRESIGNED_URL_EXPIRY_SECONDS = config("PRESIGNED_URL_EXPIRY_SECONDS", default=3600, cast=int)

# --------------------------------------------------------------------------- #
# Email (SMTP)
# --------------------------------------------------------------------------- #
EMAIL_HOST = config("EMAIL_HOST", default="")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
SENDER_EMAIL = config("SENDER_EMAIL", default="")

# --------------------------------------------------------------------------- #
# LLM providers (fallback order: Gemini API -> Vertex AI -> Claude)
# --------------------------------------------------------------------------- #
GEMINI_API_KEY = config("GEMINI_API_KEY", default="")
ANTHROPIC_API_KEY = config("ANTHROPIC_API_KEY", default="")
GCP_PROJECT = config("GOOGLE_CLOUD_PROJECT", default="")
GCP_LOCATION = config("GOOGLE_CLOUD_LOCATION", default="global")
# Self-imposed cap on Vertex calls per day (tracked in Redis).
VERTEX_DAILY_LIMIT = config("VERTEX_DAILY_LIMIT", default=1000, cast=int)
DEFAULT_LLM_MODEL = config("DEFAULT_LLM_MODEL", default="gemini-3-flash-preview")

# --------------------------------------------------------------------------- #
# Observability (OpenTelemetry -> OTLP/HTTP collector)
# --------------------------------------------------------------------------- #
OTEL_ENABLED = config("OTEL_ENABLED", default=False, cast=bool)
OTEL_ENDPOINT = config("OTEL_ENDPOINT", default="http://localhost:4318")
SERVICE_NAME = config("SERVICE_NAME", default=APP_NAME)
OBS_AUTH_TOKEN = config("OBS_AUTH_TOKEN", default="")

# --------------------------------------------------------------------------- #
# Rate limiting (slowapi)
# --------------------------------------------------------------------------- #
# Format accepted by ``limits``: "60/minute", "1000/hour", ...
RATE_LIMIT_DEFAULT = config("RATE_LIMIT_DEFAULT", default="60/minute")
