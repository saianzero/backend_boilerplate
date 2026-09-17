"""
FastAPI application entry point.

    uvicorn main:app --host 0.0.0.0 --port 8011 --reload

Startup order (``lifespan``): connect Mongo/Beanie -> start Taskiq brokers.
Shutdown reverses it and closes Redis.

Adding a module = 3 lines here:
    1. ``from src.widgets.router import router as widgets_router``
    2. ``self.app.include_router(widgets_router)``
    3. ``"src.widgets.router"`` in ``container.wire(modules=[...])``
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from src.common.logging.logging_config import setup_logger
from src.common.router import router as common_router
from src.core.class_object import singleton
from src.core.config import APP_NAME, BACKEND_CORS_ORIGINS, ROOT_PATH, TOOL_ENV
from src.core.container import Container
from src.core.redis_client import redis_client
from src.internal.router import router as internal_router
from src.items.router import router as items_router
from src.middleware.rate_limiting import setup_rate_limiting
from src.observability.bootstrap import init_observability
from src.taskiq_brokers import ALL_BROKERS

setup_logger()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = app.state.db
    await db.connect()
    logger.info("[Mongo] Connected, Beanie initialised")

    for broker in ALL_BROKERS:
        await broker.startup()
    logger.info("[Taskiq] Brokers connected to NATS")

    yield

    for broker in ALL_BROKERS:
        await broker.shutdown()
    logger.info("[Taskiq] Brokers closed")
    await db.close()
    await redis_client.aclose()
    logger.info("[Redis] Connection closed")


@singleton
class AppCreator:
    """Builds and configures the FastAPI app exactly once per process."""

    def __init__(self):
        self.container = Container()
        self.db = self.container.db()

        is_prod = TOOL_ENV == "prod"
        self.app = FastAPI(
            title=APP_NAME,
            lifespan=lifespan,
            root_path=ROOT_PATH,
            docs_url=None if is_prod else "/docs",
            openapi_url=None if is_prod else "/openapi.json",
            redoc_url=None if is_prod else "/redoc",
        )
        self.app.state.db = self.db
        init_observability(self.app)

        # ---- middleware ------------------------------------------------------
        if BACKEND_CORS_ORIGINS:
            self.app.add_middleware(
                CORSMiddleware,
                allow_origins=BACKEND_CORS_ORIGINS,
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )
        setup_rate_limiting(self.app)

        @self.app.middleware("http")
        async def add_hsts_header(request, call_next):
            response = await call_next(request)
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )
            return response

        # ---- infra routes ----------------------------------------------------
        @self.app.get("/", tags=["health"])
        def root():
            return {"service": APP_NAME, "status": "ok"}

        @self.app.get("/health", tags=["health"])
        async def health_check():
            """Liveness + Mongo ping. Returns 200 either way; inspect ``status``."""
            try:
                await self.db.ping()
                return {"status": "ok", "mongo": "connected"}
            except Exception as e:  # noqa: BLE001
                logger.exception("MongoDB connection failed")
                return {"status": "degraded", "mongo": "unreachable", "error": str(e)}

        # ---- feature routers -------------------------------------------------
        self.app.include_router(items_router)
        self.app.include_router(common_router)
        self.app.include_router(internal_router)


app_creator = AppCreator()
container = app_creator.container
db = app_creator.db
app = app_creator.app

# Modules that use ``Provide[Container.x]`` must be wired.
container.wire(
    modules=[
        "src.items.router",
        "src.common.router",
    ]
)
