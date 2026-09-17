"""
Redis-backed progress tracking for batches of background tasks.

Data layout (all keys expire after ``JOB_TTL_SECONDS``):

    job:<job_id>          hash  {status, total, completed, failed, user_id, org_id}
    job:<job_id>:tasks    hash  {<task_key>: queued|processing|completed|failed}
    job:<job_id>:errors   hash  {<task_key>: "<error message>"}
    job:<job_id>:meta     hash  free-form per-task metadata (optional)

Producer side (service):
    job_id = await JobTracker.create(user_id, org_id, total=len(items))
    for item in items:
        await JobTracker.mark(job_id, str(item.id), "queued")
        await process_item_task.kiq(str(item.id), job_id)

Consumer side (task):
    async with JobTracker.run(job_id, task_key):
        ...do the work...           # status -> processing -> completed / failed(+error)

Status endpoint:
    return await JobTracker.get(job_id, requesting_user_id=user.id)
"""

import logging
import traceback
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from src.constants import JOB_TTL_SECONDS
from src.core.redis_client import redis_client

logger = logging.getLogger(__name__)


class JobTracker:
    @staticmethod
    def _k(job_id: str, suffix: str = "") -> str:
        return f"job:{job_id}{':' + suffix if suffix else ''}"

    # ------------------------------------------------------------ lifecycle --
    @classmethod
    async def create(cls, user_id: str, org_id: str, total: int, job_id: str | None = None) -> str:
        job_id = job_id or str(uuid4())
        await redis_client.hset(
            cls._k(job_id),
            mapping={
                "status": "queued",
                "total": total,
                "completed": 0,
                "failed": 0,
                "user_id": str(user_id),
                "org_id": str(org_id),
            },
        )
        for suffix in ("", "tasks", "errors", "meta"):
            await redis_client.expire(cls._k(job_id, suffix), JOB_TTL_SECONDS)
        return job_id

    @classmethod
    async def mark(cls, job_id: str, task_key: str, status: str, error: str | None = None) -> None:
        await redis_client.hset(cls._k(job_id, "tasks"), task_key, status)
        if status == "failed":
            await redis_client.hset(cls._k(job_id, "errors"), task_key, error or "unknown error")
            await redis_client.hincrby(cls._k(job_id), "failed", 1)
        elif status == "completed":
            await redis_client.hincrby(cls._k(job_id), "completed", 1)
        await cls._maybe_finalize(job_id)

    @classmethod
    async def set_meta(cls, job_id: str, task_key: str, value: str) -> None:
        """Attach a small piece of metadata to a task (e.g. an id it produced)."""
        await redis_client.hset(cls._k(job_id, "meta"), task_key, value)

    @classmethod
    async def _maybe_finalize(cls, job_id: str) -> None:
        job = await redis_client.hgetall(cls._k(job_id)) or {}
        total = int(job.get("total", 0))
        done = int(job.get("completed", 0)) + int(job.get("failed", 0))
        if total and done >= total:
            await redis_client.hset(cls._k(job_id), "status", "completed")

    @classmethod
    @asynccontextmanager
    async def run(cls, job_id: str | None, task_key: str):
        """
        Context manager for task bodies. No-op when ``job_id`` is None so tasks
        can also be fired without tracking.
        """
        if job_id:
            await cls.mark(job_id, task_key, "processing")
        try:
            yield
        except Exception as e:  # noqa: BLE001
            logger.error(f"Task {task_key} failed: {e}\n{traceback.format_exc()}")
            if job_id:
                await cls.mark(job_id, task_key, "failed", error=str(e))
            raise
        else:
            if job_id:
                await cls.mark(job_id, task_key, "completed")

    # ----------------------------------------------------------------- read --
    @classmethod
    async def get(cls, job_id: str, requesting_user_id: str | None = None) -> dict[str, Any] | None:
        """Full snapshot. Returns ``None`` if missing or owned by another user."""
        job = await redis_client.hgetall(cls._k(job_id)) or {}
        if not job:
            return None
        if requesting_user_id and job.get("user_id") not in (None, "", str(requesting_user_id)):
            return None
        tasks = await redis_client.hgetall(cls._k(job_id, "tasks")) or {}
        errors = await redis_client.hgetall(cls._k(job_id, "errors")) or {}
        meta = await redis_client.hgetall(cls._k(job_id, "meta")) or {}
        return {
            "job_id": job_id,
            "status": job.get("status", "queued"),
            "total": int(job.get("total", 0)),
            "completed": int(job.get("completed", 0)),
            "failed": int(job.get("failed", 0)),
            "tasks": [
                {"key": k, "status": v, "error": errors.get(k), "meta": meta.get(k)}
                for k, v in tasks.items()
            ],
        }
