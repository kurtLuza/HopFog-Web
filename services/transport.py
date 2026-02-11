"""HopFog transport layer (hardware abstraction).

Your admin web app queues broadcasts in SQLite/Postgres. Later, a dispatcher
needs to deliver those broadcasts to fog nodes over *local-only* links (no
internet): Bluetooth (classic RFCOMM / BLE) today, maybe XBee/802.15.4 serial
in the future.

This module gives you:
- BaseTransport interface
- MockTransport (works without hardware; logs deliveries)
- BluetoothRFCOMMTransport (placeholder; optional dependency)

When your equipment arrives, you can implement a new class (e.g.
XBeeSerialTransport) that follows the same interface.

Design choice
-------------
We deliver broadcasts to fog nodes, not directly to residents. The fog nodes
then fan-out to resident phones (Bluetooth connection), and resident phones
ACK delivery/read back to the fog, which reports back to this server via API.

So transport.send_to_fog_node() is intentionally small.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional
import json
import logging

log = logging.getLogger("hopfog.transport")


@dataclass
class TransportResult:
    ok: bool
    detail: str = ""
    raw: Optional[Any] = None


class BaseTransport:
    """Transport interface used by the dispatcher."""

    def send_to_fog_node(self, fog_node_id: str, payload: dict[str, Any]) -> TransportResult:
        """Deliver a payload to a fog node.

        Parameters
        ----------
        fog_node_id:
            A stable fog identifier (e.g., "fog-1", BT MAC, etc.).
        payload:
            JSON-serializable dict.

        Returns
        -------
        TransportResult
        """
        raise NotImplementedError


class MockTransport(BaseTransport):
    """Non-hardware transport. Always succeeds and logs payload."""

    def send_to_fog_node(self, fog_node_id: str, payload: dict[str, Any]) -> TransportResult:
        try:
            log.info("[MOCK] send_to_fog_node fog=%s payload=%s", fog_node_id, json.dumps(payload)[:8000])
            return TransportResult(ok=True, detail="mock_ok")
        except Exception as e:
            return TransportResult(ok=False, detail=f"mock_error: {type(e).__name__}: {e}")


class BluetoothRFCOMMTransport(BaseTransport):
    """Classic Bluetooth RFCOMM (serial) transport placeholder.

    Implementation note:
      - This expects the fog node to expose a serial service.
      - You can use PyBluez (bluetooth package) if available.

    To keep the repo runnable without hardware, this class fails cleanly if
    the dependency isn't installed.
    """

    def __init__(self, mac_address: str, port: int = 1, timeout_s: int = 10):
        self.mac_address = mac_address
        self.port = port
        self.timeout_s = timeout_s

    def send_to_fog_node(self, fog_node_id: str, payload: dict[str, Any]) -> TransportResult:
        try:
            import bluetooth  # type: ignore
        except Exception:
            return TransportResult(
                ok=False,
                detail="PyBluez not installed. Install 'pybluez' or use MockTransport.",
            )

        try:
            data = (json.dumps(payload) + "\n").encode("utf-8")
            sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
            sock.settimeout(self.timeout_s)
            sock.connect((self.mac_address, self.port))
            sock.send(data)
            sock.close()
            return TransportResult(ok=True, detail="rfcomm_sent")
        except Exception as e:
            return TransportResult(ok=False, detail=f"rfcomm_error: {type(e).__name__}: {e}")
