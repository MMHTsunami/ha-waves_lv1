"""Constants for the Waves eMotion LV1 integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "waves_lv1"
SERVICE_FADE_FADER: Final = "fade_fader"
SERVICE_SEND_RAW_OSC: Final = "send_raw_osc"

CONF_SELECTED: Final = "selected"
CONF_ENABLED_GROUPS: Final = "enabled_groups"

# --- Entity group categories, selectable in the options flow ---
GROUP_CHANNELS: Final = "channels"
GROUP_GROUPS: Final = "groups"
GROUP_AUXES: Final = "auxes"
GROUP_MAINS: Final = "mains"
GROUP_MATRICES: Final = "matrices"
GROUP_DCAS: Final = "dcas"
GROUP_AUX_SENDS: Final = "aux_sends"
GROUP_MUTE_GROUPS: Final = "mute_groups"
GROUP_USER_KEYS: Final = "user_keys"
GROUP_SCENES: Final = "scenes"
GROUP_GLOBAL: Final = "global"

ENTITY_GROUP_LABELS: Final[dict[str, str]] = {
    GROUP_CHANNELS: "Channels",
    GROUP_GROUPS: "Groups",
    GROUP_AUXES: "Auxes",
    GROUP_MAINS: "Mains (LR / Center / Mono / Cue / Talkback)",
    GROUP_MATRICES: "Matrices",
    GROUP_DCAS: "DCAs",
    GROUP_AUX_SENDS: "Aux Sends",
    GROUP_MUTE_GROUPS: "Mute Groups",
    GROUP_USER_KEYS: "User Keys",
    GROUP_SCENES: "Scenes",
    GROUP_GLOBAL: "Global (Tempo, Flip, Topology, Transport)",
}

# Every group is created by default; the user narrows this down via the options flow.
DEFAULT_ENABLED_GROUPS: Final[list[str]] = list(ENTITY_GROUP_LABELS)

# --- OSC-over-TCP framing (reverse-engineered from LV1 captures) ---
# Frame = [4B big-endian payload length][8B header][N bytes OSC payload].
# The length field covers only the OSC payload, not the 8-byte header.
TCP_HEADER_LEN: Final = 8
TCP_TX_HEADER: Final = bytes([0x00, 0x00, 0x00, 0x02, 0x00, 0x00, 0x00, 0x00])
MAX_FRAME_PAYLOAD: Final = 16 * 1024 * 1024

DEFAULT_DEVICE_NAME: Final = "Home Assistant"
HANDSHAKE_ACK_TIMEOUT: Final = 3.0
TCP_CONNECT_TIMEOUT: Final = 5.0
DEFAULT_RECONNECT_DELAY: Final = 3.0
CONSECUTIVE_FAILURES_BEFORE_REDISCOVER: Final = 2

# --- zDNS discovery (custom multicast, NOT mDNS) ---
ZDNS_MULTICAST_ADDR: Final = "225.1.1.1"
ZDNS_MULTICAST_PORT: Final = 13337
ZDNS_SERVICE_TYPE: Final = "_waveslv113._tcp"
ZDNS_DEFAULT_TIMEOUT: Final = 6.0

# --- OSC addresses used by the protocol/handshake layer ---
ADDR_PING: Final = "/ping"
ADDR_PONG: Final = "/pong"
ADDR_HANDSHAKE: Final = "/handshake"
ADDR_DEVICE_NAME: Final = "/device_name"
ADDR_ZDNS: Final = "/zDNS"

# --- Topology fallbacks, mirroring effectiveChannels()/effectiveAuxes() in main.ts ---
# Used for entity/dropdown population before the LV1's /Notify/Layers + /Aux/Tracks
# arrive (or after a reconnect clears the previously detected topology).
DEFAULT_INPUT_CHANNELS: Final = 80
DEFAULT_AUX_CHANNELS: Final = 32
