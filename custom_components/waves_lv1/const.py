"""Constants for the Waves eMotion LV1 integration."""
from typing import Final

DOMAIN: Final = "waves_lv1"

# Connection Defaults
DEFAULT_PORT: Final = 13337
DEFAULT_DISCOVERY_TIMEOUT: Final = 5.0
RECONNECT_DELAY_BASE: Final = 2.0
MAX_RECONNECT_ATTEMPTS_BEFORE_REDISCOVER: Final = 3

# OSC Protocol Framing (Reverse Engineered Bytes)
# Length Header (4 Bytes BE) + Header Payload (8 Bytes)
OSC_HEADER_BYTES: Final = bytes([0x00, 0x00, 0x00, 0x02, 0x00, 0x00, 0x00, 0x00])
HEADER_SIZE: Final = 8

# Multicast zDNS Service Tag
ZDNS_SERVICE_TYPE: Final = "_waveslv113._tcp"
ZDNS_MCAST_IP: Final = "224.0.0.251"
ZDNS_MCAST_PORT: Final = 5353
