"""
Repository for the generic ``File`` document.

Adds duplicate-detection helpers on top of ``BaseRepository``.
"""

from src.common.models.file import File
from src.common.repositories.base_repository import BaseRepository


class FileRepository(BaseRepository[File]):
    model = File

    async def get_by_hashed_content(self, org_id: str, hashed_content: str) -> File | None:
        return await File.find_one(File.org_id == org_id, File.hashed_content == hashed_content)

    async def list_by_file_size_range(
        self, org_id: str, min_size: int, max_size: int
    ) -> list[File]:
        """Cheap first pass for duplicate detection before hashing."""
        return await File.find(
            File.org_id == org_id,
            File.file_size >= min_size,
            File.file_size <= max_size,
        ).to_list()

    async def get_all(self, org_id: str) -> list[File]:
        return await File.find(File.org_id == org_id).to_list()
