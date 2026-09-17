"""
JSON logging to stdout. Call ``setup_logger()`` once per process (API and each
worker). Trace/span ids are added to each line when OTEL is enabled.

    import logging
    logger = logging.getLogger(__name__)
    logger.info("item created", extra={"item_id": item_id})   # extra fields are ignored by the
                                                              # formatter; put context in the message
"""

import json
import logging
import sys
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    """Formats each log record as a single JSON line.

    OTEL's LoggingInstrumentor injects otelTraceID / otelSpanID into the
    record after this formatter runs, but the BatchLogRecordProcessor on the
    OTEL side captures them independently, so Loki will always have trace
    correlation regardless of what we emit to stdout.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(
                timespec="milliseconds"
            ),
            "level": record.levelname,
            "logger": record.name,
            "function": f"{record.funcName}:{record.lineno}",
            "message": record.getMessage(),
        }

        # Include trace / span IDs when OTEL LoggingInstrumentor has injected them
        for field in (
            "otelTraceID",
            "otelSpanID",
            "otelTraceSampled",
            "trace_id",
            "span_id",
            "traceparent",
        ):
            value = getattr(record, field, None)
            if value:
                payload[field] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        elif record.exc_text:
            payload["exception"] = record.exc_text

        return json.dumps(payload, ensure_ascii=False)


def setup_logger():
    """Sets up the root logger with a JSON stream handler."""
    handler = logging.StreamHandler(sys.stdout)
    formatter = JsonFormatter()
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    # root_logger.handlers = [handler]
    root_logger.addHandler(handler)

    # Silence noisy third-party loggers
    logging.getLogger("pymongo").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("opentelemetry").setLevel(logging.CRITICAL)
