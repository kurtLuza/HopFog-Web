"""Broadcast dispatcher.

This worker pulls queued broadcasts from the DB and delivers them to fog nodes
using a transport adapter.

Right now (no equipment), it can run with MockTransport and still update:
- broadcast_messages.status
- broadcast_recipients.status + timestamps
- broadcast_events

Later, you'll replace MockTransport with an actual Bluetooth/XBee transport.

Important: this dispatcher is *best-effort* and intentionally simple. It is
meant to make your hardware integration easier, not to be a perfect MQ.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy import asc, desc

from database.connection import SessionLocal
from database.models import BroadcastMessage, BroadcastRecipient, BroadcastEvent
from services.transport import BaseTransport, MockTransport


def _utcnow():
    return datetime.now(timezone.utc)


def get_transport() -> BaseTransport:
    """Choose transport based on env vars.

    DISPATCH_TRANSPORT=mock (default)
    DISPATCH_TRANSPORT=bt_rfcomm requires BT_MAC and optional BT_PORT.

    You can extend this with XBee later.
    """
    t = (os.getenv("DISPATCH_TRANSPORT") or "mock").lower()

    if t == "mock":
        return MockTransport()

    if t in {"bt", "bluetooth", "bt_rfcomm", "rfcomm"}:
        from services.transport import BluetoothRFCOMMTransport

        mac = os.getenv("BT_MAC")
        if not mac:
            # Fail closed but keep server running.
            return MockTransport()
        port = int(os.getenv("BT_PORT") or "1")
        return BluetoothRFCOMMTransport(mac_address=mac, port=port)

    return MockTransport()


def _select_next_broadcast(db: Session) -> BroadcastMessage | None:
    """Pick the next queued broadcast.

    Order:
      1) highest priority
      2) oldest created first
    """
    now = _utcnow()

    q = (
        db.query(BroadcastMessage)
        .filter(BroadcastMessage.status == "queued")
        .order_by(desc(BroadcastMessage.priority), asc(BroadcastMessage.created_at))
    )

    # TTL filter: only send if ttl_expires_at is null OR not expired.
    # (SQLite stores tz-naive sometimes; handle safely.)
    items = q.limit(20).all()
    for b in items:
        if b.ttl_expires_at:
            try:
                if b.ttl_expires_at.replace(tzinfo=timezone.utc) < now:
                    b.status = "failed"
                    db.add(BroadcastEvent(broadcast_id=b.id, event_type="ttl_expired", message="TTL expired before dispatch"))
                    db.commit()
                    continue
            except Exception:
                # If timezone issues occur, skip TTL enforcement rather than crash.
                pass
        return b

    return None


def _build_payload(b: BroadcastMessage) -> dict[str, Any]:
    return {
        "type": "broadcast",
        "broadcast_id": b.id,
        "msg_type": b.msg_type,
        "severity": b.severity,
        "subject": b.subject,
        "body": b.body,
        "created_at": b.created_at.isoformat() if b.created_at else None,
        "ttl_expires_at": b.ttl_expires_at.isoformat() if b.ttl_expires_at else None,
    }


async def dispatch_once(fog_node_id: str = "fog-1") -> dict[str, Any]:
    """One dispatch cycle (callable from API/manual testing)."""
    transport = get_transport()
    db = SessionLocal()
    try:
        b = _select_next_broadcast(db)
        if not b:
            return {"dispatched": False, "reason": "no_queued"}

        payload = _build_payload(b)

        # Mark attempt
        now = _utcnow()
        db.query(BroadcastRecipient).filter(BroadcastRecipient.broadcast_id == b.id).update(
            {"attempts": BroadcastRecipient.attempts + 1, "last_attempt_at": now},
            synchronize_session=False,
        )
        db.commit()

        result = transport.send_to_fog_node(fog_node_id=fog_node_id, payload=payload)

        if result.ok:
            # We consider "sent to fog" as SENT. Later the fog will update delivered/read per recipient.
            b.status = "sent"
            db.query(BroadcastRecipient).filter(BroadcastRecipient.broadcast_id == b.id).update(
                {"status": "sent", "sent_at": now},
                synchronize_session=False,
            )
            db.add(BroadcastEvent(broadcast_id=b.id, event_type="sent_to_fog", message=f"Sent to {fog_node_id} via {result.detail}"))
            db.commit()
            return {"dispatched": True, "broadcast_id": b.id, "transport": result.detail}

        # Transport failed
        b.status = "failed"
        db.query(BroadcastRecipient).filter(BroadcastRecipient.broadcast_id == b.id).update(
            {"status": "failed", "fail_reason": result.detail},
            synchronize_session=False,
        )
        db.add(BroadcastEvent(broadcast_id=b.id, event_type="dispatch_failed", message=result.detail))
        db.commit()
        return {"dispatched": False, "broadcast_id": b.id, "reason": result.detail}

    finally:
        db.close()


async def dispatcher_loop():
    """Background loop controlled by env vars.

    DISPATCHER_ENABLED=1 enables it.
    DISPATCHER_INTERVAL_S=2 (default)
    DISPATCH_FOG_ID=fog-1
    """
    enabled = (os.getenv("DISPATCHER_ENABLED") or "0") == "1"
    if not enabled:
        return

    interval = float(os.getenv("DISPATCHER_INTERVAL_S") or "2")
    fog_id = os.getenv("DISPATCH_FOG_ID") or "fog-1"

    while True:
        try:
            await dispatch_once(fog_node_id=fog_id)
        except Exception:
            # Never crash the whole server because of dispatcher.
            pass
        await asyncio.sleep(interval)


_dispatcher_task: asyncio.Task | None = None


async def start_dispatcher_background() -> None:
    """Start dispatcher loop in the background.

    Safe to call multiple times; it will only start once.
    Controlled by env var DISPATCHER_ENABLED=1.
    """
    global _dispatcher_task
    if _dispatcher_task and not _dispatcher_task.done():
        return
    # Create task even if disabled; the loop exits immediately.
    _dispatcher_task = asyncio.create_task(dispatcher_loop(), name="hopfog_dispatcher")
