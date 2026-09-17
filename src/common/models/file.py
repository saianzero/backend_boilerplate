"""
Generic uploaded-file record.

Stores metadata for anything pushed to object storage: who uploaded it, which
org owns it, and a content hash + preview for duplicate detection.
"""

from src.common.models.base import BaseDocument


class File(BaseDocument):
    file_name: str
    file_type: str  # extension or MIME type
    file_size: int  # bytes
    file_url: str  # public/S3 URL or object key
    uploaded_by: str  # user id
    org_id: str = ""  # multi-tenant isolation
    hashed_content: str = ""  # md5/sha256 of bytes - duplicate detection
    file_1024_bytes: str = ""  # text preview of first KB

    class Settings:
        name = "files"
        indexes = ["org_id", "uploaded_by", "hashed_content"]
