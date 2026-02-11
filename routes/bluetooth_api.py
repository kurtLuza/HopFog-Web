from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Dict, Optional
import time
import uuid

router = APIRouter(prefix="/api/bluetooth", tags=["bluetooth"])

# --------------------------------------------------------------------
# Bluetooth Messaging Placeholder API
#
# Purpose:
# - Let the admin web app enqueue a "Bluetooth-bound" message now,
#   even without hardware.
# - Let a future fog-node Bluetooth service poll for messages and ACK
#   results back to the server.
#
# Replace this in-memory OUTBOX with your DB or dispatcher integration
# when the equipment arrives.
# --------------------------------------------------------------------

# In-memory placeholder store (restart clears it)
BT_OUTBOX: Dict[str, Dict[str, Any]] = {}


class BluetoothSendRequest(BaseModel):
    fog_id: str = Field(..., description="Target fog node ID (e.g., fog-1)")
    channel: str = Field(..., description="announcement|alert|sos|custom")
    payload: Dict[str, Any] = Field(..., description="Message payload to be delivered to fog node")
    priority: int = Field(5, description="Lower = higher priority; SOS can be 1")


class BluetoothSendResponse(BaseModel):
    bt_msg_id: str
    status: str
    queued_at: float


class BluetoothStatusResponse(BaseModel):
    bt_msg_id: str
    status: str
    updated_at: float
    detail: Optional[str] = None
    fog_id: Optional[str] = None


@router.post("/send", response_model=BluetoothSendResponse)
def bluetooth_send(req: BluetoothSendRequest):
    """
    Admin → Server placeholder "send to bluetooth" endpoint.
    Queues the message into an in-memory outbox.
    """
    bt_msg_id = f"bt_{uuid.uuid4().hex}"
    now = time.time()

    BT_OUTBOX[bt_msg_id] = {
        "bt_msg_id": bt_msg_id,
        "fog_id": req.fog_id,
        "channel": req.channel,
        "payload": req.payload,
        "priority": req.priority,
        "status": "queued",  # queued -> sent -> acked/failed
        "queued_at": now,
        "updated_at": now,
        "detail": "Placeholder: queued in server outbox (mock)",
    }

    return BluetoothSendResponse(bt_msg_id=bt_msg_id, status="queued", queued_at=now)


@router.get("/status/{bt_msg_id}", response_model=BluetoothStatusResponse)
def bluetooth_status(bt_msg_id: str):
    item = BT_OUTBOX.get(bt_msg_id)
    if not item:
        raise HTTPException(status_code=404, detail="Bluetooth message not found")

    return BluetoothStatusResponse(
        bt_msg_id=item["bt_msg_id"],
        status=item["status"],
        updated_at=item["updated_at"],
        detail=item.get("detail"),
        fog_id=item.get("fog_id"),
    )


class BluetoothAckRequest(BaseModel):
    bt_msg_id: str
    status: str = Field(..., description="sent|acked|failed|delivered|read")
    detail: Optional[str] = None


@router.post("/ack", response_model=BluetoothStatusResponse)
def bluetooth_ack(req: BluetoothAckRequest):
    """
    Fog node → Server placeholder ACK endpoint.
    Fog node calls this after it attempts delivery.
    """
    item = BT_OUTBOX.get(req.bt_msg_id)
    if not item:
        raise HTTPException(status_code=404, detail="Bluetooth message not found")

    item["status"] = req.status
    item["updated_at"] = time.time()
    if req.detail:
        item["detail"] = req.detail

    return BluetoothStatusResponse(
        bt_msg_id=item["bt_msg_id"],
        status=item["status"],
        updated_at=item["updated_at"],
        detail=item.get("detail"),
        fog_id=item.get("fog_id"),
    )


@router.get("/outbox/next")
def bluetooth_outbox_next(fog_id: str):
    """
    Fog node polling endpoint.
    Returns the next queued message for a given fog_id.

    Example:
      GET /api/bluetooth/outbox/next?fog_id=fog-1
    """
    candidates = [
        v for v in BT_OUTBOX.values()
        if v.get("fog_id") == fog_id and v.get("status") == "queued"
    ]
    if not candidates:
        return {"message": None}

    # Highest priority first (lowest number), then FIFO
    candidates.sort(key=lambda x: (x.get("priority", 5), x.get("queued_at", 0)))
    msg = candidates[0]

    # Mark as sent once fog pulls it (optional but useful for demo)
    msg["status"] = "sent"
    msg["updated_at"] = time.time()
    msg["detail"] = "Placeholder: pulled by fog node (server marked as sent)"

    return {"message": msg}
