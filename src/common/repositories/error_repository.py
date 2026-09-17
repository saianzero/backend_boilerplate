"""
Reusable ``HTTPException`` instances.

Raise them directly from services so error text stays consistent:

    from src.common.repositories.error_repository import ErrorRepository
    raise ErrorRepository.NOT_FOUND

Add project-specific errors here rather than inlining strings in services.
"""

from fastapi import HTTPException


class ErrorRepository:
    # Generic
    NOT_FOUND = HTTPException(status_code=404, detail="Resource not found.")
    FORBIDDEN = HTTPException(
        status_code=403, detail="You do not have permission to perform this action."
    )
    INVALID_ID = HTTPException(status_code=400, detail="Invalid id format.")
    CONFLICT = HTTPException(status_code=409, detail="Resource already exists.")
    NO_INPUT = HTTPException(status_code=400, detail="No input provided.")

    # Auth
    TOKEN_EXPIRED = HTTPException(status_code=401, detail="Token has expired")
    INVALID_TOKEN = HTTPException(status_code=401, detail="Invalid or expired token")
    INVALID_CREDENTIALS = HTTPException(
        status_code=401, detail="Invalid email or password. Please try again."
    )
    USER_NOT_FOUND = HTTPException(status_code=404, detail="User not found.")
    PERMISSION_DENIED = FORBIDDEN

    # Files
    FILE_TOO_LARGE = HTTPException(status_code=400, detail="File exceeds size limit.")
    UNSUPPORTED_FILE_TYPE = HTTPException(status_code=400, detail="Unsupported file type.")
    EMPTY_FILE = HTTPException(status_code=400, detail="Uploaded file is empty.")
