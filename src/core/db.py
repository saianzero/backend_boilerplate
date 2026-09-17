"""
MongoDB connection + Beanie ODM bootstrap.

``Database.connect()`` does three things:
1. Opens a Motor client.
2. Imports every module under ``src/<module>/models/`` so that each
   ``BaseDocument`` subclass gets registered (you never list models by hand).
3. Calls ``init_beanie`` with all discovered documents.

Convention
----------
Put every Beanie document in ``src/<feature>/models/<name>.py`` and make it
inherit from ``src.common.models.base.BaseDocument``. That is all that is needed
for auto-discovery.

Transactions
------------
    async with db.session() as session:
        await Item(...).insert(session=session)
        await Other(...).insert(session=session)
    # commit on exit, rollback on exception. Requires a replica set.
"""

import importlib
import logging
import os
import pkgutil
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

from src.common.models.base import BaseDocument
from src.constants import BASE_PACKAGE as base_package

logger = logging.getLogger(__name__)


class Database:
    """Wrapper around the Motor client and Beanie initialisation."""

    def __init__(self, db_url: str, db_name: str):
        self._db_url = db_url
        self._db_name = db_name
        self._client: AsyncIOMotorClient | None = None
        self._database = None

    async def connect(self):
        """Open the connection, discover models, initialise Beanie."""
        self._client = AsyncIOMotorClient(self._db_url)
        self._database = self._client[self._db_name]
        self._import_models(base_package)
        document_models = BaseDocument.__subclasses__()
        logger.info(
            "Initialising Beanie with %d document(s): %s",
            len(document_models),
            ", ".join(m.__name__ for m in document_models),
        )
        await init_beanie(database=self._database, document_models=document_models)

    async def close(self):
        """Close the Motor client."""
        if self._client:
            self._client.close()

    async def ping(self) -> bool:
        """Cheap liveness check used by ``/health``."""
        await self._database.command("ping")
        return True

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[Any, Any]:
        """Async context manager yielding a session inside a transaction."""
        async with await self._client.start_session() as session:  # type: ignore[attr-defined]
            async with session.start_transaction():
                yield session

    def _import_models(self, base_package: str):
        """
        Import ``<base>/<feature>/models/*.py`` for every feature package so
        Beanie documents register themselves via ``BaseDocument.__subclasses__``.
        """
        for _, feature_name, is_pkg in pkgutil.iter_modules([base_package]):
            if not is_pkg:
                continue
            models_dir = os.path.join(base_package, feature_name, "models")
            if not os.path.isdir(models_dir):
                continue
            for _, model_file, _ in pkgutil.iter_modules([models_dir]):
                module_path = f"{base_package}.{feature_name}.models.{model_file}"
                try:
                    importlib.import_module(module_path)
                except Exception as e:  # noqa: BLE001
                    logger.error(f"Error importing {module_path}: {e}")
