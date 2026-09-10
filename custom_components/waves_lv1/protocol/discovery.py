"""zDNS LAN discovery for the Waves LV1, ported from zdns-discover.ts.

Standard mDNS/Bonjour does NOT work for the LV1 — only its custom "/zDNS"
OSC-formatted UDP multicast announcement (225.1.1.1:13337) does. Each
announcement carries the service type, an instance UUID, hostname, listening
TCP port, and every IPv4/IPv6 address on every NIC of the LV1 host.
"""

from __future__ import annotations

import asyncio
import re
import socket
from dataclasses import dataclass, field

from .osc import decode_packet

MULTICAST_ADDR = "225.1.1.1"
MULTICAST_PORT = 13337
DEFAULT_SERVICE_TYPE = "_waveslv113._tcp"
DEFAULT_TIMEOUT = 6.0

_IPV4_RE = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")


@dataclass(slots=True)
class DiscoveryEntry:
    """A single LV1 announcement, deduplicated by (service, host, port)."""

    service: str
    uuid: str | None
    host: str | None
    port: int | None
    addresses: list[str] = field(default_factory=list)  # IPv4, ranked best-first
    ipv6: list[str] = field(default_factory=list)
    source: str = ""  # IP the announcement actually arrived from


def _is_ipv4(value: str) -> bool:
    return bool(_IPV4_RE.match(value))


def _is_ipv6(value: str) -> bool:
    return ":" in value


def rank_ip(ip: str) -> int:
    """Rank an advertised IPv4 by how likely it is to be the real LAN address."""
    if ip.startswith("127."):
        return -100
    if ip.startswith("169.254."):
        return -50
    try:
        octets = [int(part) for part in ip.split(".")]
    except ValueError:
        return 40
    if octets[0] == 172 and 16 <= octets[1] <= 31:
        return 30  # Docker / WSL / Hyper-V
    if ip.startswith("192.168.56."):
        return 20  # VirtualBox host-only
    if ip.startswith("192.168."):
        return 100  # typical home/studio LAN
    if ip.startswith("10."):
        return 90  # corporate LAN
    return 40


def parse_zdns(data: bytes) -> DiscoveryEntry | None:
    """Parse a raw zDNS UDP payload into a DiscoveryEntry, or None if invalid."""
    try:
        message = decode_packet(data)
    except ValueError:
        return None
    if message.address != "/zDNS" or not message.args:
        return None
    if len(message.args) < 2 or message.args[0].type != "s":
        return None

    service = message.args[0].value
    uuid = message.args[1].value if len(message.args) > 1 and message.args[1].type == "s" else None

    host: str | None = None
    port: int | None = None
    ipv4s: list[str] = []
    ipv6s: list[str] = []
    for arg in message.args[2:]:
        if arg.type == "s":
            value = arg.value
            if _is_ipv4(value):
                ipv4s.append(value)
            elif _is_ipv6(value):
                ipv6s.append(value)
            elif host is None and value:
                host = value
        elif arg.type == "i" and port is None:
            candidate = arg.value
            if 1024 < candidate < 65536:
                port = candidate

    ranked = sorted(ipv4s, key=rank_ip, reverse=True)
    return DiscoveryEntry(service=service, uuid=uuid, host=host, port=port, addresses=ranked, ipv6=ipv6s)


def _local_ipv4_addresses() -> set[str]:
    """Best-effort enumeration of this host's non-loopback IPv4 addresses."""
    addresses: set[str] = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            candidate = info[4][0]
            if not candidate.startswith("127."):
                addresses.add(candidate)
    except OSError:
        pass
    # Fallback: ask the OS which interface would route to the internet
    # (no packets are actually sent for a UDP "connect").
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("8.8.8.8", 80))
            addresses.add(probe.getsockname()[0])
    except OSError:
        pass
    return addresses


class _ZDnsProtocol(asyncio.DatagramProtocol):
    def __init__(self, on_entry: "callable[[DiscoveryEntry], None]", service: str, filter_host_ip: str | None) -> None:
        self._on_entry = on_entry
        self._service = service
        self._filter_host_ip = filter_host_ip

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        entry = parse_zdns(data)
        if entry is None or entry.service != self._service:
            return
        if self._filter_host_ip and self._filter_host_ip not in entry.addresses:
            return
        entry.source = addr[0]
        self._on_entry(entry)


async def discover(
    *,
    timeout: float = DEFAULT_TIMEOUT,
    service_type: str = DEFAULT_SERVICE_TYPE,
    filter_host_ip: str | None = None,
) -> list[DiscoveryEntry]:
    """Listen for zDNS announcements for `timeout` seconds and return unique entries."""
    found: dict[str, DiscoveryEntry] = {}

    def on_entry(entry: DiscoveryEntry) -> None:
        key = f"{entry.service}|{entry.host}|{entry.port}"
        found.setdefault(key, entry)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_REUSEPORT"):
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except OSError:
            pass
    sock.bind(("", MULTICAST_PORT))

    joined_any = False
    for local_ip in _local_ipv4_addresses():
        try:
            mreq = socket.inet_aton(MULTICAST_ADDR) + socket.inet_aton(local_ip)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            joined_any = True
        except OSError:
            continue  # Some interfaces refuse multicast — ignore, like the JS client.
    if not joined_any:
        try:
            mreq = socket.inet_aton(MULTICAST_ADDR) + socket.inet_aton("0.0.0.0")
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        except OSError:
            pass

    loop = asyncio.get_event_loop()
    transport, _protocol = await loop.create_datagram_endpoint(
        lambda: _ZDnsProtocol(on_entry, service_type, filter_host_ip),
        sock=sock,
    )
    try:
        await asyncio.sleep(timeout)
    finally:
        transport.close()

    return list(found.values())
