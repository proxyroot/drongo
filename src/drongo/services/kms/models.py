"""In-memory models for Cloud KMS (key rings, crypto keys, encrypt/decrypt).

KMS defaults to gRPC but ships a REST transport, so drongo forces the client onto
REST and serves it over HTTP. Real KMS never exposes key material; the mock uses
a **reversible** encoding that embeds the key name and AAD, so ``decrypt`` returns
the original plaintext only when the same key and AAD are used - enough to test
envelope-encryption code paths without real crypto.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from drongo.core import exceptions
from drongo.core.backend import BackendDict, BaseBackend

__all__ = ["CryptoKey", "KMSBackend", "KeyRing", "kms_backends"]


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


#: The KMS client sends enums as integers (`?$alt=json;enum-encoding=int`), so a
#: crypto key's ``purpose`` arrives as a number; map the common ones to names.
_PURPOSE_NAMES = {
    1: "ENCRYPT_DECRYPT",
    5: "ASYMMETRIC_SIGN",
    6: "ASYMMETRIC_DECRYPT",
    7: "RAW_ENCRYPT_DECRYPT",
    9: "MAC",
}


def _normalize_purpose(purpose: Any) -> str:
    if isinstance(purpose, bool):
        return "ENCRYPT_DECRYPT"
    if isinstance(purpose, int):
        return _PURPOSE_NAMES.get(purpose, "CRYPTO_KEY_PURPOSE_UNSPECIFIED")
    return str(purpose) or "ENCRYPT_DECRYPT"


@dataclass
class KeyRing:
    name: str
    create_time: str = field(default_factory=_now)

    def to_resource(self) -> dict[str, Any]:
        return {"name": self.name, "createTime": self.create_time}


@dataclass
class CryptoKey:
    name: str
    purpose: str = "ENCRYPT_DECRYPT"
    labels: dict[str, str] = field(default_factory=dict)
    create_time: str = field(default_factory=_now)

    @property
    def primary_version(self) -> str:
        return f"{self.name}/cryptoKeyVersions/1"

    def to_resource(self) -> dict[str, Any]:
        resource: dict[str, Any] = {
            "name": self.name,
            "purpose": self.purpose,
            "createTime": self.create_time,
        }
        if self.labels:
            resource["labels"] = self.labels
        if self.purpose == "ENCRYPT_DECRYPT":
            resource["primary"] = {
                "name": self.primary_version,
                "state": "ENABLED",
                "algorithm": "GOOGLE_SYMMETRIC_ENCRYPTION",
                "protectionLevel": "SOFTWARE",
                "createTime": self.create_time,
            }
        return resource


class KMSBackend(BaseBackend):
    """In-memory Cloud KMS state for a single project."""

    def setup(self) -> None:
        self.key_rings: dict[str, KeyRing] = {}
        self.crypto_keys: dict[str, CryptoKey] = {}

    # -- key rings ---------------------------------------------------------

    def create_key_ring(self, parent: str, key_ring_id: str) -> KeyRing:
        name = f"{parent}/keyRings/{key_ring_id}"
        if name in self.key_rings:
            raise exceptions.already_exists(f"KeyRing already exists: {name}")
        ring = KeyRing(name=name)
        self.key_rings[name] = ring
        return ring

    def get_key_ring(self, name: str) -> KeyRing:
        try:
            return self.key_rings[name]
        except KeyError:
            raise exceptions.not_found(f"KeyRing not found: {name}")

    def list_key_rings(self, parent: str) -> list[KeyRing]:
        prefix = f"{parent}/keyRings/"
        return [
            self.key_rings[n] for n in sorted(self.key_rings) if n.startswith(prefix)
        ]

    # -- crypto keys -------------------------------------------------------

    def create_crypto_key(
        self, parent: str, crypto_key_id: str, spec: dict[str, Any]
    ) -> CryptoKey:
        name = f"{parent}/cryptoKeys/{crypto_key_id}"
        if name in self.crypto_keys:
            raise exceptions.already_exists(f"CryptoKey already exists: {name}")
        key = CryptoKey(
            name=name,
            purpose=_normalize_purpose(spec.get("purpose", "ENCRYPT_DECRYPT")),
            labels=dict(spec.get("labels") or {}),
        )
        self.crypto_keys[name] = key
        return key

    def get_crypto_key(self, name: str) -> CryptoKey:
        try:
            return self.crypto_keys[name]
        except KeyError:
            raise exceptions.not_found(f"CryptoKey not found: {name}")

    def list_crypto_keys(self, parent: str) -> list[CryptoKey]:
        prefix = f"{parent}/cryptoKeys/"
        return [
            self.crypto_keys[n]
            for n in sorted(self.crypto_keys)
            if n.startswith(prefix)
        ]

    def _resolve_key(self, name: str) -> CryptoKey:
        # Accept either a crypto-key name or a specific version name.
        key_name = name.split("/cryptoKeyVersions/", 1)[0]
        return self.get_crypto_key(key_name)

    # -- encrypt / decrypt -------------------------------------------------

    def encrypt(self, name: str, plaintext: bytes, aad: bytes) -> tuple[str, bytes]:
        key = self._resolve_key(name)
        token = base64.b64encode(
            json.dumps(
                {
                    "k": key.name,
                    "p": base64.b64encode(plaintext).decode("ascii"),
                    "a": base64.b64encode(aad).decode("ascii"),
                }
            ).encode("utf-8")
        )
        return key.primary_version, token

    def decrypt(self, name: str, ciphertext: bytes, aad: bytes) -> bytes:
        key = self._resolve_key(name)
        try:
            data = json.loads(base64.b64decode(ciphertext))
        except Exception:
            raise exceptions.bad_request("Decryption failed: malformed ciphertext")
        if data.get("k") != key.name:
            raise exceptions.bad_request(
                "Decryption failed: ciphertext is not for this key"
            )
        if base64.b64decode(data.get("a", "")) != aad:
            raise exceptions.bad_request(
                "Decryption failed: additional authenticated data mismatch"
            )
        return base64.b64decode(data["p"])


#: Project-keyed backends, inspectable via ``get_backend("kms")[project]``.
kms_backends: BackendDict[KMSBackend] = BackendDict(KMSBackend, "kms")
