"""Minimal OSC 1.0 encoder/decoder, ported from the Companion module's osc.ts.

We can't use a generic OSC library: the LV1 wraps every packet in a custom
8-byte header (see tcp_client.py) that generic OSC libraries don't expect, so
this module only handles the address/type-tag/argument wire format itself.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Union

OscValue = Union[int, float, str, bytes, bool, None]


@dataclass(frozen=True, slots=True)
class OscArg:
    """A single typed OSC argument."""

    type: str
    value: OscValue = None


@dataclass(slots=True)
class OscMessage:
    """A decoded/encodable OSC message."""

    address: str
    args: list[OscArg] = field(default_factory=list)


class OscDecodeError(ValueError):
    """Raised when a buffer cannot be decoded as an OSC message."""


def _pad_len(length: int) -> int:
    """Return the number of zero-padding bytes needed to reach a multiple of 4."""
    return (4 - (length % 4)) % 4


def _encode_string(value: str) -> bytes:
    raw = value.encode("utf-8") + b"\x00"
    return raw + b"\x00" * _pad_len(len(raw))


def _encode_blob(data: bytes) -> bytes:
    head = struct.pack(">i", len(data))
    return head + data + b"\x00" * _pad_len(len(data))


def encode_message(address: str, args: list[OscArg] | None = None) -> bytes:
    """Encode an OSC address + typed args into a wire-format buffer."""
    args = args or []
    tag = "," + "".join(a.type for a in args)
    parts: list[bytes] = [_encode_string(address), _encode_string(tag)]
    for arg in args:
        match arg.type:
            case "i":
                # Wrap to a signed 32-bit int, mirroring JS's `value | 0`.
                wrapped = ((int(arg.value) + 0x80000000) % 0x100000000) - 0x80000000
                parts.append(struct.pack(">i", wrapped))
            case "f":
                parts.append(struct.pack(">f", float(arg.value)))
            case "h":
                parts.append(struct.pack(">q", int(arg.value)))
            case "d":
                parts.append(struct.pack(">d", float(arg.value)))
            case "s":
                parts.append(_encode_string(str(arg.value)))
            case "b":
                parts.append(_encode_blob(bytes(arg.value)))  # type: ignore[arg-type]
            case "T" | "F" | "N" | "I":
                pass  # No payload bytes for these types.
            case _:
                raise ValueError(f"Unsupported OSC type tag: {arg.type!r}")
    return b"".join(parts)


def _read_string(buf: bytes, offset: int) -> tuple[str, int]:
    end = buf.find(b"\x00", offset)
    if end == -1:
        raise OscDecodeError("OSC string not null-terminated")
    value = buf[offset:end].decode("utf-8")
    total = end - offset + 1
    return value, total + _pad_len(total)


def decode_message(buf: bytes) -> OscMessage:
    """Decode a wire-format OSC message buffer."""
    offset = 0
    address, consumed = _read_string(buf, offset)
    offset += consumed
    if offset >= len(buf):
        return OscMessage(address=address, args=[])

    tag, consumed = _read_string(buf, offset)
    offset += consumed
    if not tag.startswith(","):
        return OscMessage(address=address, args=[])

    args: list[OscArg] = []
    for type_char in tag[1:]:
        if type_char == "i":
            args.append(OscArg("i", struct.unpack_from(">i", buf, offset)[0]))
            offset += 4
        elif type_char == "f":
            args.append(OscArg("f", struct.unpack_from(">f", buf, offset)[0]))
            offset += 4
        elif type_char == "h":
            args.append(OscArg("h", struct.unpack_from(">q", buf, offset)[0]))
            offset += 8
        elif type_char == "d":
            args.append(OscArg("d", struct.unpack_from(">d", buf, offset)[0]))
            offset += 8
        elif type_char == "s":
            value, consumed = _read_string(buf, offset)
            args.append(OscArg("s", value))
            offset += consumed
        elif type_char == "b":
            (blob_len,) = struct.unpack_from(">i", buf, offset)
            offset += 4
            data = buf[offset : offset + blob_len]
            args.append(OscArg("b", data))
            offset += blob_len + _pad_len(blob_len)
        elif type_char == "T":
            args.append(OscArg("T", True))
        elif type_char == "F":
            args.append(OscArg("F", False))
        elif type_char == "N":
            args.append(OscArg("N", None))
        elif type_char == "I":
            args.append(OscArg("I", float("inf")))
        else:
            # Unknown type tag — skip silently; the wire is sometimes ahead of us.
            break
    return OscMessage(address=address, args=args)


def decode_packet(buf: bytes) -> OscMessage:
    """Decode a single OSC packet. Bundles are not used by this protocol."""
    return decode_message(buf)


def int_arg(message: OscMessage, index: int) -> float | int | None:
    """Return arg[index] as a number if it is i/f/d, else None."""
    if index >= len(message.args):
        return None
    arg = message.args[index]
    if arg.type in ("i", "f", "d"):
        return arg.value  # type: ignore[return-value]
    return None


def string_arg(message: OscMessage, index: int) -> str | None:
    """Return arg[index] as a string, else None."""
    if index >= len(message.args):
        return None
    arg = message.args[index]
    return arg.value if arg.type == "s" else None  # type: ignore[return-value]


def bool_arg(message: OscMessage, index: int) -> bool | None:
    """Return arg[index] as a bool if it is T/F, else None."""
    if index >= len(message.args):
        return None
    arg = message.args[index]
    if arg.type == "T":
        return True
    if arg.type == "F":
        return False
    return None
