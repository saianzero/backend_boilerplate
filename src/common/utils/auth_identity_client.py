"""
HTTP client for the platform identity/auth service.

Use it when you need user or org details that are not in the ``x-user-data``
header (display names for a list of ids, org metadata, user search).

    client = AuthIdentityClient()
    user = await client.get_user_by_id("u1")                 # dict | None
    users = await client.lookup_users_by_ids(["u1", "u2"])   # list[dict]
    hits = await client.search_users("ada", org_id)          # list[dict]
    org = await client.get_organization_by_id(org_id)        # dict | None

Errors from the upstream service are re-raised as ``HTTPException`` with the
same status code, except 404 which becomes ``None`` for the getters.
"""

import logging

import httpx
from fastapi import HTTPException

from src.core.config import AUTH_SERVICE_URL

logger = logging.getLogger(__name__)


class AuthIdentityClient:
    def __init__(self):
        self.base_url = AUTH_SERVICE_URL

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _raise_for(self, response: httpx.Response):
        if not response.is_success:
            try:
                detail = response.json().get("detail", response.text)
            except Exception:
                detail = response.text
            raise HTTPException(status_code=response.status_code, detail=detail)

    async def _get(self, path: str, params: dict | None = None) -> dict:
        async with httpx.AsyncClient() as client:
            response = await client.get(self._url(path), params=params)
        self._raise_for(response)
        return response.json()

    async def _post(self, path: str, body: dict) -> dict:
        async with httpx.AsyncClient() as client:
            response = await client.post(self._url(path), json=body)
        self._raise_for(response)
        return response.json()

    async def get_user_by_id(self, user_id: str) -> dict | None:
        try:
            return await self._get("/get-user", params={"user_id": str(user_id)})
        except HTTPException as exc:
            if exc.status_code == 404:
                return None
            raise

    async def lookup_users_by_ids(
        self,
        ids: list[str],
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[dict]:
        if not ids:
            return []
        body: dict = {"ids": [str(i) for i in ids]}
        if limit is not None:
            body["limit"] = limit
        if offset is not None:
            body["offset"] = offset
        data = await self._post("/users:lookup-by-ids", body)
        return data.get("users", [])

    async def search_users(self, query: str, org_id: str) -> list[dict]:
        if not query or len(query.strip()) < 2:
            return []
        data = await self._get(
            "/search-users",
            params={"q": query.strip(), "org_id": str(org_id)},
        )
        return data.get("users", [])

    async def get_organization_by_id(self, org_id: str) -> dict | None:
        try:
            return await self._get("/get-organization", params={"id": str(org_id)})
        except HTTPException as exc:
            if exc.status_code == 404:
                return None
            raise
