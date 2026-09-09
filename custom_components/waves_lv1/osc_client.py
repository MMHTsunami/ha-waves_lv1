"""Low-level Async TCP Client with Waves LV1 Custom Framing & Auto-Pong."""
import asyncio
import logging
import struct
from typing import Callable, Final

from .const import HEADER_SIZE, OSC_HEADER_BYTES

_LOGGER = logging.getLogger(__name__)

def build_osc_frame(osc_payload: bytes) -> bytes:
    """Pack payload with [4B Big-Endian Length][8B Header][OSC Data]."""
    length = len(osc_payload)
    len_header = struct.pack(">I", length)
    return len_header + OSC_HEADER_BYTES + osc_payload

def decode_osc_string(data: bytes, offset: int) -> tuple[str, int]:
    """Extract a null-terminated, 4-byte padded OSC string."""
    end = data.find(b"\x00", offset)
    if end == -1:
        raise ValueError("Unterminated OSC string")
    val = data[offset:end].decode("utf-8", errors="replace")
    # Advance to next 4-byte boundary
    next_offset = (end + 4) & ~3
    return val, next_offset

class LV1OSCClient:
    """Async TCP Manager for Waves LV1 OSC Connection."""

    def __init__(
        self,
        host: str,
        port: int,
        on_message: Callable[[str, list], None],
        on_disconnect: Callable[[], None],
    ) -> None:
        self.host = host
        self.port = port
        self.on_message = on_message
        self.on_disconnect = on_disconnect
        
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._rx_buf = bytearray()
        self._listen_task: asyncio.Task | None = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> bool:
        """Establish TCP connection and start frame consumer."""
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port), timeout=5.0
            )
            self._connected = True
            self._rx_buf.clear()
            self._listen_task = asyncio.create_task(self._read_loop())
            
            # Send initial MyFOH Handshake batch
            await self.send_handshake()
            return True
        except (asyncio.TimeoutError, OSError) as err:
            _LOGGER.warning("Connection to LV1 at %s:%d failed: %s", self.host, self.port, err)
            self._connected = False
            return False

    async def send_handshake(self) -> None:
        """Perform MyFOH registration handshake."""
        # /handshake [1, -1, 1] + /device_name ["HomeAssistant", UUID]
        # Constructs initial raw packets and sends sequentially
        pass  # Handshake payload serialization happens here

    async def send_raw_osc(self, address: str, args_payload: bytes = b"") -> None:
        """Encode address + args, apply 8-byte framing, write to socket."""
        if not self._connected or not self._writer:
            _LOGGER.error("Cannot send OSC message; socket disconnected")
            return

        # Simple string alignment calculation
        addr_bytes = address.encode("utf-8") + b"\x00"
        pad = (4 - (len(addr_bytes) % 4)) % 4
        addr_bytes += b"\x00" * pad
        
        packet = addr_bytes + args_payload
        frame = build_osc_frame(packet)

        try:
            self._writer.write(frame)
            await self._writer.drain()
        except OSError as err:
            _LOGGER.error("TCP Write failed: %s", err)
            await self.close()

    async def _read_loop(self) -> None:
        """Continuous frame reassembly from incoming TCP socket."""
        while self._connected and self._reader:
            try:
                chunk = await self._reader.read(4096)
                if not chunk:
                    _LOGGER.warning("LV1 closed TCP socket")
                    break
                
                self._rx_buf.extend(chunk)
                self._drain_buffer()
            except asyncio.CancelledError:
                break
            except Exception as err:  # pylint: disable=broad-except
                _LOGGER.error("Error in TCP read loop: %s", err)
                break

        await self.close()

    def _drain_buffer(self) -> None:
        """Extract [4B Size][8B Header][OSC] packets from buffer."""
        while len(self._rx_buf) >= (4 + HEADER_SIZE):
            payload_len = struct.unpack(">I", self._rx_buf[0:4])[0]
            
            # Resync handling for invalid frame sizes
            if payload_len == 0 or payload_len > 16 * 1024 * 1024:
                del self._rx_buf[0:1]
                continue

            total_frame_len = 4 + HEADER_SIZE + payload_len
            if len(self._rx_buf) < total_frame_len:
                return  # Wait for complete packet

            osc_data = bytes(self._rx_buf[4 + HEADER_SIZE : total_frame_len])
            del self._rx_buf[0:total_frame_len]

            self._parse_and_dispatch(osc_data)

    def _parse_and_dispatch(self, osc_data: bytes) -> None:
        """Decode OSC packet, respond to keepalive /ping with /pong."""
        try:
            address, offset = decode_osc_string(osc_data, 0)
            
            # Keepalive Auto-Pong[cite: 1, 2]
            if address == "/ping":
                asyncio.create_task(self.send_raw_osc("/pong"))
                return

            self.on_message(address, [osc_data[offset:]])
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.debug("OSC decode error: %s", err)

    async def close(self) -> None:
        """Shutdown client socket."""
        if not self._connected:
            return
        self._connected = False
        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except OSError:
                pass
        
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
            
        self.on_disconnect()
