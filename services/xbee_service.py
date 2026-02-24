# services/xbee_service.py
import os
import json
import threading
import time
from digi.xbee.devices import XBeeDevice


class XBeeService:

    def __init__(self):
        self.port = os.getenv("XBEE_PORT", "COM5")  # change for every device
        self.baud = int(os.getenv("XBEE_BAUD", "9600"))
        self._lock = threading.Lock()
        self.device: XBeeDevice | None = None

        # Raw RX buffer (for debugging / backward compatibility)
        self._rx = []  # list of dicts

        # Parsed HopFog messages (structured JSON from ESP32)
        self._parsed_messages = []

        # Reassembly buffer for fragmented XBee packets
        self._reassembly_buffer = ""
        self._buffer_lock = threading.Lock()

    def open(self):
        with self._lock:
            if self.device and self.device.is_open():
                return
            self.device = XBeeDevice(self.port, self.baud)
            self.device.open()
            self.device.add_data_received_callback(self._on_receive)
            print(f"[XBee] Opened {self.port} @ {self.baud} baud")

    def _on_receive(self, xbee_message):
        """Called by digi-xbee reader thread.
        MUST NOT raise exceptions — if it does, the reader thread dies
        permanently and no more callbacks will ever fire."""
        try:
            try:
                text = xbee_message.data.decode(errors="replace")
            except Exception:
                text = "<decode error>"

            raw_item = {
                "text": text,
                "from_64bit": str(xbee_message.remote_device.get_64bit_addr()),
                "ts": time.time(),
            }

            self._rx.append(raw_item)
            if len(self._rx) > 200:
                self._rx = self._rx[-200:]

            print(f"[XBee RX raw] ({len(text)} bytes): {text[:200]}")

            # Append to reassembly buffer and try to extract complete packets
            with self._buffer_lock:
                self._reassembly_buffer += text
                self._extract_packets(raw_item["from_64bit"])

        except Exception as e:
            # CATCH EVERYTHING — never let the reader thread die
            print(f"[XBee CRITICAL] Callback error (reader thread preserved): {e}")

    def _extract_packets(self, from_addr: str):
        """Extract complete <<HOPFOG_START>>...<<HOPFOG_END>> packets
        from the reassembly buffer. Handles:
        - Full packet in one callback
        - Packet split across 2-3 callbacks (fragmentation)
        - Multiple packets in one callback
        - Garbage data before/between packets (ESP32 boot noise)
        """
        START = "<<HOPFOG_START>>"
        END = "<<HOPFOG_END>>"

        while True:
            start_idx = self._reassembly_buffer.find(START)

            if start_idx < 0:
                # No start marker — discard everything (garbage / boot noise)
                if len(self._reassembly_buffer) > 0:
                    print(f"[XBee] No START marker, discarding {len(self._reassembly_buffer)} bytes")
                self._reassembly_buffer = ""
                break

            # Discard anything before the start marker
            if start_idx > 0:
                garbage = self._reassembly_buffer[:start_idx]
                print(f"[XBee] Discarding {len(garbage)} bytes before START: {garbage[:50]}")
                self._reassembly_buffer = self._reassembly_buffer[start_idx:]

            end_idx = self._reassembly_buffer.find(END)

            if end_idx < 0:
                # Have START but no END yet — wait for more fragments
                print(f"[XBee] Have START but waiting for END... buffer={len(self._reassembly_buffer)} bytes")
                break

            # Extract the JSON between markers
            json_str = self._reassembly_buffer[len(START):end_idx].strip()

            # Remove the processed packet from the buffer
            self._reassembly_buffer = self._reassembly_buffer[end_idx + len(END):].strip()

            # Parse the JSON
            try:
                packet = json.loads(json_str)
                packet["_from_addr"] = from_addr
                packet["_received_at"] = time.time()

                self._parsed_messages.append(packet)
                if len(self._parsed_messages) > 500:
                    self._parsed_messages = self._parsed_messages[-500:]

                ptype = packet.get("type", "unknown")
                print(f"[XBee PARSED] type={ptype}")
                self._handle_packet(packet)

            except json.JSONDecodeError as e:
                print(f"[XBee] JSON parse error: {e}")
                print(f"[XBee] Raw string: {json_str[:200]}")

        # Safety: prevent buffer from growing forever
        if len(self._reassembly_buffer) > 4096:
            print("[XBee] Buffer overflow, clearing")
            self._reassembly_buffer = ""

    def _handle_packet(self, packet: dict):
        """Route parsed packets to the appropriate handler."""
        ptype = packet.get("type", "")
        data = packet.get("data", {})

        if ptype == "message":
            print(f"  MSG from {data.get('sender_username')} "
                  f"in conv {data.get('conversation_id')}: "
                  f"{data.get('message_text')}")

        elif ptype == "sos_alert":
            print(f"  SOS ALERT from {data.get('username')} "
                  f"(user_id={data.get('user_id')}) "
                  f"priority={data.get('priority')}")

        elif ptype == "login":
            print(f"  LOGIN: {data.get('username')} "
                  f"(user_id={data.get('user_id')})")

        elif ptype == "new_chat":
            print(f"  NEW CHAT: {data.get('user1_name')} <-> {data.get('user2_name')}")

        elif ptype == "node_online":
            print(f"  ESP32 ONLINE: SSID={data.get('ssid')}, IP={data.get('ip')}")

        else:
            print(f"  Unknown type: {ptype}")

    def close(self):
        with self._lock:
            if self.device and self.device.is_open():
                self.device.close()
                print("[XBee] Device closed")

    def info(self):
        if not self.device or not self.device.is_open():
            return {"error": "XBee not connected"}
        return {
            "port": self.port,
            "baud": self.baud,
            "64bit_addr": str(self.device.get_64bit_addr()),
            "node_id": self.device.get_node_id(),
        }

    def send_broadcast(self, text: str):
        if not self.device or not self.device.is_open():
            raise Exception("XBee not connected")
        self.device.send_data_broadcast(text)
        return {"sent": True, "text": text}

    # Expose RX buffer for API
    def get_received(self):
        return list(self._rx)

    # Expose parsed messages for API
    def get_parsed_messages(self):
        return list(self._parsed_messages)

    def clear_received(self):
        self._rx.clear()
        self._parsed_messages.clear()
        with self._buffer_lock:
            self._reassembly_buffer = ""
        return {"cleared": True}


# Singleton — used by xbee_api.py and app/main.py
xbee_service = XBeeService()


def send_broadcast(text: str):
    return xbee_service.send_broadcast(text)
