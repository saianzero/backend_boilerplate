"""Request bodies for creating items (plain and via presigned upload)."""

from pydantic import BaseModel, Field


class CreateItemRequest(BaseModel):
    """Simple JSON create (no file)."""

    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    tags: list[str] = []
    metadata: dict | None = None


class PresignRequest(BaseModel):
    """Step 1 of file upload: ask for a PUT url per file."""

    file_name: str
    file_type: str  # MIME type the browser will send
    file_size: int


class UploadedItemRequest(BaseModel):
    """Step 2: confirm the upload so the server creates the Item + queues processing."""

    file_data: PresignRequest
    aws_object_name: str  # returned by step 1
    name: str | None = None  # defaults to file_name
    tags: list[str] = []
