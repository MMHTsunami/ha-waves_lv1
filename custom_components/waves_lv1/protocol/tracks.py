"""Track/group topology helpers, ported from tracks.ts.

The LV1 has a fixed set of numbered "groups" (input, group bus, aux/FX, the
five masters, matrix, DCA) plus one pseudo-group (13) used only to multiplex
mute-group state onto the `/Notify/Track/Out/Mute` address. Two groups have a
variable channel count reported by the LV1 itself (Input, Aux); the rest are
fixed-size or singletons (a single master track).
"""

from __future__ import annotations

from typing import Final

GROUP_TAG: Final[dict[int, str]] = {
    0: "In",
    1: "Grp",
    2: "Aux",
    3: "LR",
    4: "C",
    5: "M",
    6: "Mtx",
    7: "Cue",
    8: "TB",
    12: "DCA",
}

GROUP_SLUG: Final[dict[int, str]] = {
    0: "in",
    1: "grp",
    2: "aux",
    3: "lr",
    4: "c",
    5: "m",
    6: "mtx",
    7: "cue",
    8: "tb",
    12: "dca",
}

# Prefixes used for entity display names (distinct from GROUP_TAG's Companion-style tags).
ENTITY_GROUP_PREFIX: Final[dict[int, str]] = {
    0: "CH",
    1: "GRP",
    2: "AUX",
    3: "LR",
    4: "C",
    5: "M",
    6: "MTX",
    7: "Cue",
    8: "TB",
    12: "DCA",
}

# Groups the LV1 always has a fixed channel count for, regardless of mixer mode.
FIXED_GROUP_COUNTS: Final[dict[int, int]] = {1: 8, 6: 8, 12: 8}

# Pseudo-group the LV1 multiplexes mute-group state onto (see coordinator.py).
MUTE_GROUP_PSEUDO_GROUP: Final = 13

_SINGLETON_GROUPS: Final = frozenset({3, 4, 5, 7, 8})


def is_singleton_group(group: int) -> bool:
    """Whether `group` has exactly one track (the LR/C/M/Cue/TB masters)."""
    return group in _SINGLETON_GROUPS


def track_slug(group: int, ch: int) -> str:
    """Variable-name-safe slug for a track, e.g. `in3`, `aux12`, `lr` (singleton)."""
    prefix = GROUP_SLUG.get(group, f"g{group}")
    if is_singleton_group(group):
        return prefix
    return f"{prefix}{ch + 1}"


def track_label(group: int, ch: int, name: str | None = None) -> str:
    """Human-readable label for a track, e.g. `In 3 — Kick`, `LR — Master`."""
    tag = GROUP_TAG.get(group, f"g{group}")
    if is_singleton_group(group):
        return f"{tag} — Master"
    return f"{tag} {ch + 1} — {name}" if name else f"{tag} {ch + 1}"


def track_entity_prefix(group: int, ch: int) -> str:
    """Entity-name prefix for a track, e.g. `CH3`, `AUX12`, `LR` (singleton, no index)."""
    tag = ENTITY_GROUP_PREFIX.get(group, f"G{group}")
    if is_singleton_group(group):
        return tag
    return f"{tag}{ch + 1}"


def user_key_label(func: str | None) -> str:
    """Short display label for a user key's assigned function, e.g. `Flip Sends`."""
    if not func:
        return "Unassigned"
    return func.split(":", 1)[0].strip() or "Unassigned"


def enumerate_tracks(input_count: int, aux_count: int) -> list[tuple[int, int]]:
    """Every real (group, ch) track on this LV1, 0-based, given detected counts."""
    tracks: list[tuple[int, int]] = []
    tracks += [(0, i) for i in range(input_count)]
    tracks += [(1, i) for i in range(FIXED_GROUP_COUNTS[1])]
    tracks += [(2, i) for i in range(aux_count)]
    tracks += [(3, 0), (4, 0), (5, 0)]  # LR, Center, Mono masters
    tracks += [(6, i) for i in range(FIXED_GROUP_COUNTS[6])]
    tracks += [(7, 0), (8, 0)]  # Cue, TalkBack masters
    tracks += [(12, i) for i in range(FIXED_GROUP_COUNTS[12])]
    return tracks
