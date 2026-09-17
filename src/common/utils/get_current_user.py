"""
FastAPI dependency that resolves the caller from the ``x-user-data`` header.

The gateway authenticates the request (JWT/session) and forwards the claims as
JSON in ``x-user-data``. This service trusts that header, so it must only be
reachable through the gateway.

    @router.get("/me")
    async def me(user: CurrentUser = Depends(get_current_user)):
        return user

Local testing with curl:
    curl -H 'x-user-data: {"user_id":"u1","org_id":"o1","role":"Admin","email":"a@b.c"}' \
         http://localhost:8011/items/list
"""

import json

from fastapi import Header, HTTPException
from pydantic import ValidationError

from src.common.schemas.internal.current_user import CurrentUser


async def get_current_user(user_data: str = Header(..., alias="x-user-data")) -> CurrentUser:
    try:
        data = json.loads(user_data)
        if not isinstance(data, dict):
            raise ValueError("x-user-data must be a JSON object")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid user data in headers")

    user_id = data.get("user_id") or data.get("id")
    org_id = data.get("org_id")
    if not user_id or not org_id:
        raise HTTPException(status_code=400, detail="Missing user ID or organization ID in headers")

    # Only pass keys that are present so CurrentUser defaults apply to the rest.
    optional = {
        k: data[k]
        for k in (
            "role",
            "user_status",
            "username",
            "email",
            "email_cannonical",
            "name",
            "color",
            "platform_roles",
        )
        if data.get(k) is not None
    }
    try:
        return CurrentUser(id=str(user_id), org_id=str(org_id), **optional)
    except ValidationError as e:
        raise HTTPException(
            status_code=400, detail=f"Invalid user data in headers: {e.errors()[0]['msg']}"
        )
