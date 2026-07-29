"""Small helpers shared across services."""

from __future__ import annotations

import base64
import hashlib
import struct
from datetime import datetime, timezone


def now_rfc3339() -> str:
    """Current UTC time as an RFC 3339 string, e.g. ``2026-07-28T12:00:00.000Z``."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def md5_base64(data: bytes) -> str:
    """Base64-encoded MD5 digest (the format GCS uses for ``md5Hash``)."""
    return base64.b64encode(hashlib.md5(data).digest()).decode("ascii")


def crc32c_base64(data: bytes) -> str | None:
    """Base64 big-endian CRC32C, or ``None`` if ``google-crc32c`` is unavailable.

    GCS reports CRC32C for every object. The pure-Python fallback keeps gato
    dependency-free; when ``google-crc32c`` (a transitive dep of the storage
    client) is importable we use it for speed and exactness.
    """
    try:
        import google_crc32c

        checksum = google_crc32c.value(data)
    except ImportError:  # pragma: no cover - fallback path
        checksum = _crc32c_python(data)
    return base64.b64encode(struct.pack(">I", checksum)).decode("ascii")


# --- Pure-Python CRC32C (Castagnoli) fallback -----------------------------

_CRC32C_TABLE: list[int] = []


def _build_crc32c_table() -> None:
    poly = 0x82F63B78
    for n in range(256):
        crc = n
        for _ in range(8):
            crc = (crc >> 1) ^ poly if crc & 1 else crc >> 1
        _CRC32C_TABLE.append(crc)


def _crc32c_python(data: bytes) -> int:
    if not _CRC32C_TABLE:
        _build_crc32c_table()
    crc = 0xFFFFFFFF
    for byte in data:
        crc = (crc >> 8) ^ _CRC32C_TABLE[(crc ^ byte) & 0xFF]
    return crc ^ 0xFFFFFFFF
