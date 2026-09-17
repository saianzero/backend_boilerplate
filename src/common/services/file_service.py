"""
Generic upload/store/delete flow for files.

Flow for ``upload_file``:
1. Stream ``UploadFile`` to a temp file (``FileUtil``).
2. Two-phase duplicate check: size-range candidates first, hash only if needed.
3. Push to S3, persist a ``File`` document, clean temp file.

Reuse ``detect_duplicate`` from other services that store their own file
metadata (see ``ItemService``).
"""

import hashlib
import logging
from typing import Any

from fastapi import UploadFile

from src.common.models.file import File
from src.common.repositories.file_repository import FileRepository
from src.common.schemas.internal.current_user import CurrentUser
from src.common.utils.aws_utils import AwsUtil
from src.common.utils.file_utils import FileUtil

logger = logging.getLogger(__name__)


def md5_of_file(path: str) -> str:
    h = hashlib.new("md5", usedforsecurity=False)
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


class FileService:
    def __init__(self, file_repository: FileRepository, aws_utils: AwsUtil):
        self.repo = file_repository
        self.aws_util = aws_utils

    async def upload_file(self, file: UploadFile, user: CurrentUser) -> dict[str, Any]:
        file_util = FileUtil(file)
        try:
            file_size = file_util.get_file_size()
            file_hash = file_util.get_file_hash(algo="md5")

            existing = await self.detect_duplicate(user.org_id, file_size, file_hash)
            if existing:
                return {
                    "status": "duplicate",
                    "file_id": str(existing.id),
                    "message": "File already exists",
                }

            file_url = self.aws_util.upload_file(
                filepath=file_util.filepath,
                key=file_util.filename,
                content_type=file.content_type or "",
            )
            created = await self.repo.create(
                File(
                    file_name=file_util.filename,
                    file_type=file_util.file_ext,
                    file_size=file_size,
                    file_url=file_url,
                    uploaded_by=str(user.id),
                    org_id=user.org_id,
                    hashed_content=file_hash,
                    file_1024_bytes=file_util.preview(),
                )
            )
            return {"status": "success", "file_id": str(created.id), "file_url": created.file_url}
        finally:
            file_util.cleanup()

    async def detect_duplicate(self, org_id: str, file_size: int, file_hash: str):
        """Size-window pre-filter (+-1 KB) then exact hash match."""
        tolerance = 1024
        candidates = await self.repo.list_by_file_size_range(
            org_id=org_id, min_size=max(file_size - tolerance, 0), max_size=file_size + tolerance
        )
        if not candidates:
            return None
        return await self.repo.get_by_hashed_content(org_id, file_hash)

    async def get(self, file_id: str, user: CurrentUser) -> File | None:
        doc = await self.repo.get_by_id(file_id)
        if not doc or doc.org_id != user.org_id:
            return None
        return doc

    async def delete(self, file_id: str, user: CurrentUser) -> dict[str, Any]:
        doc = await self.get(file_id, user)
        if not doc:
            return {"status": "error", "message": "File not found or unauthorized"}
        self.aws_util.delete_object(doc.file_url)
        deleted = await self.repo.delete(file_id, user.org_id)
        return {"status": "deleted" if deleted else "error"}

    async def delete_many(self, file_ids: list[str], user: CurrentUser) -> dict[str, Any]:
        docs = await self.repo.get_many_by_ids(file_ids, org_id=user.org_id)
        for doc in docs:
            self.aws_util.delete_object(doc.file_url)
        deleted = await self.repo.delete_many([str(d.id) for d in docs], org_id=user.org_id)
        return {"status": "success", "deleted_count": deleted}

    async def list(self, user: CurrentUser) -> list[File]:
        return await self.repo.get_all(user.org_id)
