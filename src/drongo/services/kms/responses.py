"""HTTP handlers implementing the Cloud KMS REST (v1) API.

The default client is gRPC; drongo forces it onto its REST transport during a
mock scope (see ``__init__.py``). This layer also handles the base64 encoding of
byte fields and the crc32c integrity checks the KMS client performs on encrypt
and decrypt.
"""

from __future__ import annotations

import base64
from typing import Any

from drongo.core.responses import BaseResponse, HttpResponse, Request, json_response
from drongo.services.kms.models import KMSBackend, kms_backends


def _crc32c(data: bytes) -> str:
    import google_crc32c

    # REST/JSON represents the int64 crc as a string.
    return str(google_crc32c.value(data))


class KMSResponse(BaseResponse):
    """Handles Cloud KMS REST requests against the in-memory backend."""

    def backend_for(self, request: Request) -> KMSBackend:
        return kms_backends[request.path_params["project"]]

    def _location(self, request: Request) -> str:
        p = request.path_params
        return f"projects/{p['project']}/locations/{p['location']}"

    def _key_ring(self, request: Request) -> str:
        return f"{self._location(request)}/keyRings/{request.path_params['keyring']}"

    def _crypto_key(self, request: Request) -> str:
        return (
            f"{self._key_ring(request)}/cryptoKeys/{request.path_params['cryptokey']}"
        )

    # -- key rings ---------------------------------------------------------

    def create_key_ring(self, request: Request) -> HttpResponse:
        ring = self.backend_for(request).create_key_ring(
            self._location(request), request.param("keyRingId") or ""
        )
        return json_response(ring.to_resource())

    def get_key_ring(self, request: Request) -> HttpResponse:
        ring = self.backend_for(request).get_key_ring(self._key_ring(request))
        return json_response(ring.to_resource())

    def list_key_rings(self, request: Request) -> HttpResponse:
        rings = self.backend_for(request).list_key_rings(self._location(request))
        return json_response({"keyRings": [r.to_resource() for r in rings]})

    # -- crypto keys -------------------------------------------------------

    def create_crypto_key(self, request: Request) -> HttpResponse:
        key = self.backend_for(request).create_crypto_key(
            self._key_ring(request),
            request.param("cryptoKeyId") or "",
            request.json(),
        )
        return json_response(key.to_resource())

    def get_crypto_key(self, request: Request) -> HttpResponse:
        key = self.backend_for(request).get_crypto_key(self._crypto_key(request))
        return json_response(key.to_resource())

    def list_crypto_keys(self, request: Request) -> HttpResponse:
        keys = self.backend_for(request).list_crypto_keys(self._key_ring(request))
        return json_response({"cryptoKeys": [k.to_resource() for k in keys]})

    # -- encrypt / decrypt -------------------------------------------------

    def encrypt(self, request: Request) -> HttpResponse:
        body: dict[str, Any] = request.json()
        plaintext = base64.b64decode(body.get("plaintext", ""))
        aad = base64.b64decode(body.get("additionalAuthenticatedData", ""))
        version, ciphertext = self.backend_for(request).encrypt(
            self._crypto_key(request), plaintext, aad
        )
        response = {
            "name": version,
            "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
            "ciphertextCrc32c": _crc32c(ciphertext),
            "verifiedPlaintextCrc32c": True,
            "protectionLevel": "SOFTWARE",
        }
        if aad:
            response["verifiedAdditionalAuthenticatedDataCrc32c"] = True
        return json_response(response)

    def decrypt(self, request: Request) -> HttpResponse:
        body: dict[str, Any] = request.json()
        ciphertext = base64.b64decode(body.get("ciphertext", ""))
        aad = base64.b64decode(body.get("additionalAuthenticatedData", ""))
        plaintext = self.backend_for(request).decrypt(
            self._crypto_key(request), ciphertext, aad
        )
        return json_response(
            {
                "plaintext": base64.b64encode(plaintext).decode("ascii"),
                "plaintextCrc32c": _crc32c(plaintext),
                "usedPrimary": True,
                "protectionLevel": "SOFTWARE",
            }
        )
