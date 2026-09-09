"""zDNS Multicast Scanner for auto-discovering Waves LV1 mixers."""
import asyncio
import logging
import socket
import struct
from typing import Any

from .const import ZDNS_MCAST_IP, ZDNS_MCAST_PORT, ZDNS_SERVICE_TYPE

_LOGGER = logging.getLogger(__name__)

class LV1DiscoveryProtocol(asyncio.DatagramProtocol):
    """UDP listener for zDNS Multicast packets emitted by the LV1."""

    def __init__(self, target_service: str = ZDNS_SERVICE_TYPE) -> None:
        self.target_service = target_service
        self.discovered_devices: dict[str, dict[str, Any]] = {}
        self.transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        self.transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        """Parse raw zDNS packet payload."""
        try:
            payload = data.decode("utf-8", errors="ignore")
            if self.target_service in payload:
                # Basic string metadata extraction fallback from zDNS payload
                ip_addr = addr[0]
                # Default fallback port if omitted in string payload
                port = 13337 
                
                device_key = f"{ip_addr}:{port}"
                if device_key not in self.discovered_devices:
                    _LOGGER.debug("Discovered LV1 mixer at %s:%d", ip_addr, port)
                    self.discovered_devices[device_key] = {
                        "host": ip_addr,
                        "port": port,
                    }
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.debug("Failed parsing zDNS packet: %s", err)

async def async_discover_lv1(timeout: float = 3.0) -> list[dict[str, Any]]:
    """Scan local network for Waves LV1 mixers."""
    loop = asyncio.get_running_loop()
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, 
                    socket.inet_aton(ZDNS_MCAST_IP) + socket.inet_aton("0.0.0.0"))
    sock.bind(("", ZDNS_MCAST_PORT))
    sock.setblocking(False)

    transport, protocol = await loop.create_datagram_endpoint(
        lambda: LV1DiscoveryProtocol(), sock=sock
    )

    try:
        await asyncio.sleep(timeout)
    finally:
        transport.close()

    return list(protocol.discovered_devices.values())
