from __future__ import annotations

"""Fog Node API.

These endpoints are meant for:
- Fog nodes pulling queued broadcasts to deliver to residents locally
- Fog nodes reporting per-recipient delivery/read/fail acknowledgements

This lets you fully test your admin web app + message queue/tracking without
hardware. When your equipment arrives, your fog-node program just needs to:

1) call GET /api/fog/broadcasts/next?fog_id=fog-1
2) deliver that payload to resident phones over Bluetooth
3) POST /api/fog/broadcasts/ack with delivery statuses

Security note
-------------
In a real deployment, you should authenticate fog nodes. For now we keep it
simple: fog_id is accepted as-is.
"""

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func

from database.deps import get_db
from database.models import BroadcastMessage, BroadcastRecipient, BroadcastEvent

router = APIRouter(prefix="/api/fog", tags=["Fog API"])


def _utcnow():
    return datetime.now(timezone.utc)


class RecipientAck(BaseModel):
    user_id: int
    status: str = Field(..., description="sent|delivered|read|failed")
    fail_reason: Optional[str] = None


class BroadcastAck(BaseModel):
    fog_id: str
    broadcast_id: int
    recipients: List[RecipientAck]


@router.get("/broadcasts/next")
def get_next_broadcast(
    fog_id: str,
    db: Session = Depends(get_db),
):
    """Return the next QUEUED broadcast payload.

    In this simple version, every fog node sees the same queue, and it is okay
    if multiple fog nodes pull the same broadcast (you can refine later).

    Returned payload is what the fog node should deliver to resident phones.
    """

    now = _utcnow()

    # pick highest priority then oldest created
    b = (
        db.query(BroadcastMessage)
        .filter(BroadcastMessage.status == "queued")
        .filter((BroadcastMessage.ttl_expires_at.is_(None)) | (BroadcastMessage.ttl_expires_at > now))
        .order_by(BroadcastMessage.priority.desc(), BroadcastMessage.created_at.asc())
        .first()
    )

    if not b:
        return {"ok": True, "broadcast": None}

    # Provide a minimal payload. Fog nodes can deliver to all residents.
    payload = {
        "broadcast_id": b.id,
        "type": b.msg_type,
        "severity": b.severity,
        "subject": b.subject,
        "body": b.body,
        "created_at": b.created_at.isoformat() if b.created_at else None,
        "ttl_expires_at": b.ttl_expires_at.isoformat() if b.ttl_expires_at else None,
    }

    db.add(BroadcastEvent(broadcast_id=b.id, event_type="fog_pulled", message=f"Pulled by {fog_id}"))
    db.commit()

    return {"ok": True, "broadcast": payload}


@router.post("/broadcasts/ack")
def ack_broadcast(
    payload: BroadcastAck,
    db: Session = Depends(get_db),
):
    """Update per-recipient status for a broadcast."""

    b = db.query(BroadcastMessage).filter(BroadcastMessage.id == payload.broadcast_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Broadcast not found")

    now = _utcnow()

    updated = 0
    for r in payload.recipients:
        br = (
            db.query(BroadcastRecipient)
            .filter(BroadcastRecipient.broadcast_id == payload.broadcast_id)
            .filter(BroadcastRecipient.user_id == r.user_id)
            .first()
        )
        if not br:
            continue

        status = (r.status or "").lower()
        if status not in {"sent", "delivered", "read", "failed"}:
            continue

        br.status = status
        if status == "sent" and br.sent_at is None:
            br.sent_at = now
        if status == "delivered" and br.delivered_at is None:
            br.delivered_at = now
        if status == "read" and br.read_at is None:
            br.read_at = now
        if status == "failed":
            br.fail_reason = (r.fail_reason or "").strip()[:255] if r.fail_reason else "failed"

        updated += 1

    db.add(BroadcastEvent(
        broadcast_id=b.id,
        event_type="fog_ack",
        message=f"ACK from {payload.fog_id}: updated {updated} recipient(s)",
    ))
    db.commit()

    # Optional: if everyone is delivered/read/failed (no queued), mark broadcast sent.
    remaining = db.query(func.count(BroadcastRecipient.id)).filter(
        BroadcastRecipient.broadcast_id == b.id,
        BroadcastRecipient.status.in_(["queued"]),
    ).scalar() or 0

    if remaining == 0 and b.status == "queued":
        b.status = "sent"
        db.add(BroadcastEvent(broadcast_id=b.id, event_type="completed", message="No queued recipients remaining"))
        db.commit()

    return {"ok": True, "updated": updated}
