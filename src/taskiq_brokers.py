"""
Taskiq brokers backed by NATS JetStream.

One JetStream *stream* per service, one *subject* (and one broker) per logical
queue. Workers subscribe to a single subject so you can scale queues
independently (e.g. a heavy "documents" queue with 2 workers and a light
"notifications" queue with 1).

Define a queue
--------------
1. Add its id to ``SUBJECT_IDS`` below.
2. Create the broker: ``widgets_broker = create_broker("widgets")``.
3. Decorate tasks in ``src/<module>/tasks.py``:

       from src.taskiq_brokers import widgets_broker

       @widgets_broker.task(task_name="process_widget")
       async def process_widget_task(widget_id: str, job_id: str | None = None):
           ...

4. Start/stop the broker in ``main.lifespan`` (needed to *publish*).
5. Run a worker (needed to *consume*):

       taskiq worker --workers 2 --max-async-tasks 50 --ack-type when_received \
           src.taskiq_brokers:widgets_broker src.widgets.tasks

Publish a task from a service
-----------------------------
    from src.items.tasks import process_item_task
    await process_item_task.kiq(item_id, job_id)   # returns immediately

Worker lifecycle
----------------
``startup_callback`` runs once per worker process: it configures logging,
observability and connects Beanie so tasks can use models/repositories exactly
like request handlers do.
"""

from logging import getLogger

from nats.js.api import ConsumerConfig, RetentionPolicy, StorageType, StreamConfig
from taskiq import TaskiqEvents, TaskiqState
from taskiq.instrumentation import TaskiqInstrumentor
from taskiq_nats import PullBasedJetStreamBroker

from src.common.logging.logging_config import setup_logger
from src.core.config import NATS_SERVER_HOST, NATS_STREAM_NAME
from src.observability.bootstrap import init_observability

TaskiqInstrumentor().instrument()

logger = getLogger(__name__)

# Every queue this service owns. Subject = "<STREAM>.<id>".
SUBJECT_IDS = ("items",)

_MAX_MSGS = 10**4
_SUBJECTS = [f"{NATS_STREAM_NAME}.{sid}" for sid in SUBJECT_IDS]

_STREAM_CONFIG = StreamConfig(
    subjects=_SUBJECTS,
    storage=StorageType.FILE,  # persist to disk
    max_msgs=_MAX_MSGS,
    retention=RetentionPolicy.LIMITS,  # drop oldest once max_msgs reached
)


def create_broker(subject_id: str) -> PullBasedJetStreamBroker:
    """Build a pull-based JetStream broker bound to ``<STREAM>.<subject_id>``."""
    if subject_id not in SUBJECT_IDS:
        raise ValueError(f"Unknown subject id '{subject_id}'. Add it to SUBJECT_IDS.")

    subject = f"{NATS_STREAM_NAME}.{subject_id}"
    broker = PullBasedJetStreamBroker(
        servers=f"nats://{NATS_SERVER_HOST}",
        stream_name=NATS_STREAM_NAME,
        subject=subject,
        durable=subject_id,
        stream_config=_STREAM_CONFIG,
        consumer_config=ConsumerConfig(filter_subject=subject),
    )

    async def startup_callback(state: TaskiqState):
        """Worker-process bootstrap: logging, OTEL, DB/Beanie."""
        # Imported lazily to avoid a circular import (container -> services -> tasks -> brokers).
        from src.core.container import Container

        try:
            setup_logger()
            init_observability()
            container = Container()
            db = container.db()
            state.db = db
            await db.connect()
            logger.info(f"[Taskiq] Worker ready on subject '{subject}'")
        except Exception as e:  # noqa: BLE001
            logger.exception(f"[Taskiq] Worker startup failed: {e}")
            raise

    async def shutdown_callback(state: TaskiqState):
        db = getattr(state, "db", None)
        if db:
            await db.close()

    broker.add_event_handler(TaskiqEvents.WORKER_STARTUP, startup_callback)
    broker.add_event_handler(TaskiqEvents.WORKER_SHUTDOWN, shutdown_callback)
    return broker


# One broker per queue. Add more as SUBJECT_IDS grows.
items_broker = create_broker("items")

# Everything main.py must start/stop.
ALL_BROKERS = (items_broker,)
