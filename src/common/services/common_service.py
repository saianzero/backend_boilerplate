"""
Cross-module service: global search and user lookups.

Aggregates results from several feature services so the frontend can hit one
endpoint. Add a new feature's search by injecting its service and merging its
result dict here.
"""

import logging

from src.common.schemas.internal.current_user import CurrentUser
from src.common.utils.auth_identity_client import AuthIdentityClient
from src.items.services.item_service import ItemService

logger = logging.getLogger(__name__)


class CommonService:
    def __init__(self, item_service: ItemService, auth_identity_client: AuthIdentityClient):
        self.item_service = item_service
        self.auth_identity_client = auth_identity_client

    async def global_search(
        self, q: str, user: CurrentUser, page: int = 1, page_size: int = 10
    ) -> dict:
        """Merge search results from every feature module."""
        item_results = await self.item_service.search(q, user, page, page_size)
        return {"items": item_results}

    async def get_usernames(self, q: str, org_id: str) -> list[dict]:
        return await self.auth_identity_client.search_users(q, org_id)
