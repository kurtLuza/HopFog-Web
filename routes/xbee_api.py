from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from services.xbee_service import xbee_service  # singleton, NOT the class

router = APIRouter(prefix="/api/xbee", tags=["xbee"])
# NO duplicate XBeeService() here — uses the singleton from xbee_service.py


class BroadcastReq(BaseModel):
    text: str


@router.get("/info")
def info():
    try:
        return xbee_service.info()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test-broadcast")
def test_broadcast(req: BroadcastReq):
    try:
        return xbee_service.send_broadcast(req.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/broadcast")
def broadcast(req: BroadcastReq):
    try:
        return xbee_service.send_broadcast(req.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/received")
def received():
    """Raw received text from XBee (for debugging)."""
    try:
        return {"messages": xbee_service.get_received()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/parsed")
def parsed_messages():
    """Structured messages parsed from ESP32 HopFog protocol.
    Returns <<HOPFOG_START>>...<<HOPFOG_END>> packets with JSON extracted."""
    try:
        return {"messages": xbee_service.get_parsed_messages()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/received/clear")
def clear_received():
    try:
        return xbee_service.clear_received()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))