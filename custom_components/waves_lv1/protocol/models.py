"""State dataclasses mirroring the in-memory maps `main.ts` keeps on the instance."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ChannelState:
    """Per-track state, keyed by (group, ch) in `LV1Coordinator.channels`."""

    muted: bool = False
    gain: float = 0.0  # dB
    solo: bool = False
    color: tuple[float, float, float] | None = None
    name: str | None = None
    pan: float = 0.0  # -1 (full L) .. +1 (full R), 0 = center
    width: float = 1.0  # 0 (mono) .. 1 (full stereo)


@dataclass(slots=True)
class SendState:
    """Per-(track, aux) send state, keyed by (group, ch, aux) in `.sends`."""

    on: bool = False
    gain: float = -144.0


@dataclass(slots=True)
class UserKeyInfo:
    """One of the LV1's 16 user-assignable keys, from `/Notify/UserKeyInfo`."""

    name: str
    func: str
    assigned: bool


@dataclass(slots=True)
class FlipTarget:
    """Track currently flipped to the fader strip; coordinator uses None for default LR."""

    group: int
    ch: int


@dataclass(slots=True)
class DetectedTopology:
    """Mixer topology as reported by the LV1 itself — no user config needed.

    Reset to a fresh instance on every reconnect since a mixer-mode change
    (e.g. 16ch -> 80ch) can change all of these.
    """

    channels: int | None = None
    auxes: int | None = None
    aux_names: list[str] = field(default_factory=list)
