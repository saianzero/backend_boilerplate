"""
OpenTelemetry bootstrap. Call ``init_observability(app)`` once at startup.
"""

import logging

from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from src.core.config import OBS_AUTH_TOKEN, OTEL_ENABLED, OTEL_ENDPOINT, SERVICE_NAME, TOOL_ENV

logger = logging.getLogger(__name__)


def init_observability(app=None):
    """
    Configure OpenTelemetry traces, metrics and logs and export them over
    OTLP/HTTP to ``OTEL_ENDPOINT``. Auto-instruments FastAPI (when ``app`` is
    given) and outbound httpx. Taskiq is instrumented in ``taskiq_brokers``.

    No-op when ``OTEL_ENABLED`` is false (local dev default).
    """
    if not OTEL_ENABLED:
        logger.info("[OTEL] disabled (OTEL_ENABLED=false)")
        return None

    resource = Resource.create(
        {
            "service.name": SERVICE_NAME,
            "deployment.environment": TOOL_ENV,
        }
    )

    # ── Traces ────────────────────────────────────────────────────
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(
                endpoint=f"{OTEL_ENDPOINT}/v1/traces", headers={"x-auth-token": OBS_AUTH_TOKEN}
            )
        )
    )
    trace.set_tracer_provider(tracer_provider)

    # ── Metrics ───────────────────────────────────────────────────
    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(
            endpoint=f"{OTEL_ENDPOINT}/v1/metrics", headers={"x-auth-token": OBS_AUTH_TOKEN}
        ),
        export_interval_millis=15000,  # every 15 seconds
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    # Injects trace_id and span_id into every log record automatically
    LoggingInstrumentor().instrument(set_logging_format=True)

    # ── Logs ──────────────────────────────────────────────────────
    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(
        BatchLogRecordProcessor(
            OTLPLogExporter(
                endpoint=f"{OTEL_ENDPOINT}/v1/logs", headers={"x-auth-token": OBS_AUTH_TOKEN}
            )
        )
    )
    set_logger_provider(logger_provider)  # register globally so the provider isn't GC'd

    # Attach OTel log handler to root Python logger
    # This makes every logging.info() / logging.error() etc. go to the collector
    handler = LoggingHandler(level=logging.NOTSET, logger_provider=logger_provider)
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)

    # ── Auto-instrument FastAPI + outbound HTTP ───────────────────
    if app:
        FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()

    return tracer_provider, meter_provider, logger_provider
