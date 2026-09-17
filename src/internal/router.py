"""
Internal webhooks called by the platform (not by end users).

Requests are authenticated with an HMAC-SHA256 signature of the raw body using
``WEBHOOK_SHARED_SECRET``, sent in the ``x-webhook-signature`` header.

Register every tenant-scoped model in ``OWNED_MODELS`` so ownership transfer
and org deletion stay complete as the codebase grows.

Sending a test event locally:
    BODY='{"org_id":"o1"}'
    SIG=$(printf "%s" "$BODY" | openssl dgst -sha256 -hmac "$WEBHOOK_SHARED_SECRET" | sed 's/^.* //')
    curl -X POST localhost:8011/internal/org-deleted -H "x-webhook-signature: $SIG" -d "$BODY"
"""

import hashlib
import hmac
import logging

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from src.common.models.file import File
from src.core.config import WEBHOOK_SHARED_SECRET
from src.items.models.item import Item

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"])

# (model, owner_field). Every document type that stores a user id + org id.
OWNED_MODELS = [
    (Item, "uploaded_by"),
    (File, "uploaded_by"),
]


class UserDeletedEvent(BaseModel):
    user_id: str
    org_id: str
    first_admin_user_id: str | None = None  # new owner; falls back to user_id


class OrgDeletedEvent(BaseModel):
    org_id: str


def _verify_signature(raw_body: bytes, signature: str | None) -> None:
    if not WEBHOOK_SHARED_SECRET:
        logger.warning("[INTERNAL WEBHOOK] WEBHOOK_SHARED_SECRET not set; refusing request")
        raise HTTPException(status_code=503, detail="Webhook secret not configured")
    if not signature:
        raise HTTPException(status_code=401, detail="Missing signature")
    expected = hmac.new(WEBHOOK_SHARED_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")


@router.post("/user-deleted")
async def user_deleted(request: Request, x_webhook_signature: str | None = Header(default=None)):
    """Transfer everything the deleted user owned to ``first_admin_user_id``."""
    raw = await request.body()
    _verify_signature(raw, x_webhook_signature)
    event = UserDeletedEvent.model_validate_json(raw)
    new_owner = event.first_admin_user_id or event.user_id
    logger.info(f"[INTERNAL WEBHOOK] user.deleted user_id={event.user_id} org_id={event.org_id}")

    for model, owner_field in OWNED_MODELS:
        await model.find({owner_field: event.user_id, "org_id": event.org_id}).update_many(
            {"$set": {owner_field: new_owner}}
        )
    return {"status": "ok"}


@router.post("/org-deleted")
async def org_deleted(request: Request, x_webhook_signature: str | None = Header(default=None)):
    """Hard-delete every document belonging to the org."""
    raw = await request.body()
    _verify_signature(raw, x_webhook_signature)
    event = OrgDeletedEvent.model_validate_json(raw)
    logger.info(f"[INTERNAL WEBHOOK] org.deleted org_id={event.org_id}")

    for model, _ in OWNED_MODELS:
        await model.find({"org_id": event.org_id}).delete()
    return {"status": "ok"}
