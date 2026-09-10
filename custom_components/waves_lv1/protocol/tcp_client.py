"""Framed OSC-over-TCP client for the Waves LV1, ported from osc-tcp.ts.

FRAMING (reverse-engineered from real LV1 captures):
    [4-byte big-endian length][8-byte proprietary header][N bytes OSC payload]

`length` covers only the OSC payload (does not include the 8-byte header).
The LV1 also expects a keepalive: it sends `/ping [h:sysclock, i:seq]` at
~1 Hz and drops the link after ~5 s if the client doesn't echo it back as
`/pong` with the same args.

Registration is a two-flavour handshake (MyMon vs MyFOH); this client only
implements MyFOH (single batched write of `/handshake` + `/device_name`),
matching what the Companion module uses by default.
"""

from __future__ import annotations

import asyncio
import logging
import struct
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from .osc import OscArg, OscMessage, decode_packet, encode_message

_LOGGER = logging.getLogger(__name__)

TCP_HEADER_LEN = 8
TCP_TX_HEADER = bytes([0x00, 0x00, 0x00, 0x02, 0x00, 0x00, 0x00, 0x00])
MAX_FRAME_PAYLOAD = 16 * 1024 * 1024
HANDSHAKE_ACK_TIMEOUT = 3.0
TCP_CONNECT_TIMEOUT = 5.0
DEFAULT_RECONNECT_DELAY = 3.0

PacketListener = Callable[[OscMessage], Any]
EventListener = Callable[..., Any]

OscOutMessage = tuple[str, list[OscArg]]


class LV1TcpClient:
    """Async, auto-reconnecting, auto-ponging OSC-over-TCP client."""

    def __init__(
        self,
        host: str,
        port: int,
        *,
        device_name: str = "Home Assistant",
        client_uuid: str | None = None,
        auto_reconnect: bool = True,
        reconnect_delay: float = DEFAULT_RECONNECT_DELAY,
    ) -> None:
        self.host = host
        self.port = port
        self._device_name = device_name
        self._uuid = client_uuid or str(uuid.uuid4()).upper()
        self._auto_reconnect = auto_reconnect
        self._reconnect_delay = reconnect_delay

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self._reconnect_task: asyncio.Task[None] | None = None
        self._destroyed = False
        self._connected = False

        self._listeners: dict[str, list[EventListener]] = {}

    @property
    def connected(self) -> bool:
        """Whether the TCP link (not necessarily the handshake) is up."""
        return self._connected

    def on(self, event: str, callback: EventListener) -> None:
        """Register a callback for "connect"/"registered"/"close"/"error"/"packet"."""
        self._listeners.setdefault(event, []).append(callback)

    def _emit(self, event: str, *args: Any) -> None:
        for callback in self._listeners.get(event, []):
            result = callback(*args)
            if isinstance(result, Awaitable):
                asyncio.ensure_future(result)

    async def connect(self) -> None:
        """Open the TCP connection and kick off the handshake."""
        if self._writer is not None:
            return
        self._destroyed = False
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=TCP_CONNECT_TIMEOUT,
            )
        except (TimeoutError, OSError) as err:
            self._emit("error", err)
            # Node's net.Socket emits 'close' after a failed connect too; without
            # this, a run of failed reconnect attempts (e.g. the LV1 restarting
            # on a new port) would never increment a close-based failure counter.
            self._emit("close", True)
            self._schedule_reconnect()
            return

        self._connected = True
        self._emit("connect", self.host, self.port)
        self._reader_task = asyncio.ensure_future(self._read_loop())
        asyncio.ensure_future(self._register())

    def disconnect(self) -> None:
        """Tear down the connection and stop auto-reconnecting."""
        self._destroyed = True
        self._auto_reconnect = False
        if self._reconnect_task is not None:
            self._reconnect_task.cancel()
            self._reconnect_task = None
        if self._writer is not None:
            self._writer.close()
        if self._reader_task is not None:
            self._reader_task.cancel()

    def update_target(self, host: str, port: int) -> None:
        """Point the client at a new host/port (e.g. after LV1 port change)."""
        changed = host != self.host or port != self.port
        self.host = host
        self.port = port
        if changed and self._writer is not None:
            self._writer.close()  # `_read_loop`'s close handling will reconnect.

    def send(self, address: str, args: list[OscArg] | None = None) -> None:
        """Send a single OSC message, framed with the LV1's 8-byte header."""
        if not self._connected or self._writer is None:
            self._emit("error", RuntimeError(f"send({address}) while not connected"))
            return
        self._writer.write(self._frame(address, args or []))
        self._emit("sent", address, args or [])

    def send_batch(self, messages: list[OscOutMessage]) -> None:
        """Send several OSC messages in a single TCP write (required for handshakes)."""
        if not self._connected or self._writer is None:
            self._emit("error", RuntimeError("send_batch while not connected"))
            return
        self._writer.write(b"".join(self._frame(addr, args) for addr, args in messages))
        for address, args in messages:
            self._emit("sent", address, args)

    @staticmethod
    def _frame(address: str, args: list[OscArg]) -> bytes:
        payload = encode_message(address, args)
        length = struct.pack(">I", len(payload))
        return length + TCP_TX_HEADER + payload

    async def _register(self) -> None:
        """MyFOH-style handshake: batch `/handshake` + `/device_name` in one write."""
        try:
            ack_future: asyncio.Future[OscMessage] = asyncio.get_event_loop().create_future()

            def on_packet(message: OscMessage) -> None:
                if (
                    not ack_future.done()
                    and message.address == "/handshake"
                    and message.args
                    and message.args[0].type == "i"
                    and message.args[0].value == 1
                ):
                    ack_future.set_result(message)

            self.on("packet", on_packet)
            try:
                self.send_batch(
                    [
                        (
                            "/handshake",
                            [OscArg("i", 1), OscArg("i", -1), OscArg("i", 1)],
                        ),
                        (
                            "/device_name",
                            [OscArg("s", self._device_name), OscArg("s", self._uuid)],
                        ),
                    ]
                )
                try:
                    await asyncio.wait_for(ack_future, timeout=HANDSHAKE_ACK_TIMEOUT)
                except TimeoutError:
                    self._emit("error", RuntimeError("No /handshake ACK after 3 s"))
                    # Force the connection closed so `_read_loop` sees EOF and runs
                    # its normal close/reconnect handling — otherwise a TCP link
                    # that connects but never acks (e.g. a stale port now serving
                    # something else) would sit "connected" forever.
                    if self._writer is not None:
                        self._writer.close()
                    return
            finally:
                self._listeners.get("packet", []).remove(on_packet)

            self._emit("registered", "myfoh")
        except Exception as err:  # noqa: BLE001 - surfaced to caller via "error"
            self._emit("error", err)

    async def _read_loop(self) -> None:
        assert self._reader is not None
        buffer = b""
        had_error = False
        try:
            while True:
                chunk = await self._reader.read(65536)
                if not chunk:
                    break
                buffer = self._drain(buffer + chunk)
        except (OSError, asyncio.IncompleteReadError) as err:
            had_error = True
            self._emit("error", err)
        finally:
            self._connected = False
            if self._writer is not None:
                self._writer.close()
            self._writer = None
            self._reader = None
            self._emit("close", had_error)
            self._schedule_reconnect()

    def _drain(self, buffer: bytes) -> bytes:
        while len(buffer) >= 4 + TCP_HEADER_LEN:
            (size,) = struct.unpack_from(">I", buffer, 0)
            if size == 0 or size > MAX_FRAME_PAYLOAD:
                buffer = buffer[1:]  # Resync — drop one byte and retry.
                continue
            total = 4 + TCP_HEADER_LEN + size
            if len(buffer) < total:
                return buffer
            packet = buffer[4 + TCP_HEADER_LEN : total]
            buffer = buffer[total:]

            try:
                decoded = decode_packet(packet)
            except ValueError as err:
                self._emit("decode-error", err, packet)
                continue

            self._emit("packet", decoded)
            if decoded.address == "/ping":
                self.send("/pong", decoded.args)
        return buffer

    def _schedule_reconnect(self) -> None:
        if not self._auto_reconnect or self._destroyed:
            return
        self._reconnect_task = asyncio.ensure_future(self._reconnect_after_delay())

    async def _reconnect_after_delay(self) -> None:
        await asyncio.sleep(self._reconnect_delay)
        if not self._destroyed:
            await self.connect()
