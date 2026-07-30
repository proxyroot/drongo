"""Cloud KMS tests using the default client (drongo forces it to REST)."""

from __future__ import annotations

import pytest
from google.api_core import exceptions as gexc

from drongo import get_backend

pytestmark = pytest.mark.usefixtures("drongo")

LOCATION = "projects/test-project/locations/us-central1"


def _client():
    from google.cloud import kms

    return kms.KeyManagementServiceClient()


def _key(client, ring_id="kr", key_id="k1"):
    ring = client.create_key_ring(request={"parent": LOCATION, "key_ring_id": ring_id})
    from google.cloud import kms

    return client.create_crypto_key(
        request={
            "parent": ring.name,
            "crypto_key_id": key_id,
            "crypto_key": {"purpose": kms.CryptoKey.CryptoKeyPurpose.ENCRYPT_DECRYPT},
        }
    )


# -- key rings / crypto keys ------------------------------------------------


def test_create_key_ring_and_key() -> None:
    client = _client()
    key = _key(client, key_id="only")  # creates ring "kr" + key "only"
    assert key.name == f"{LOCATION}/keyRings/kr/cryptoKeys/only"
    assert key.primary.name.endswith("/cryptoKeyVersions/1")

    ring = client.create_key_ring(request={"parent": LOCATION, "key_ring_id": "kr2"})
    assert ring.name == f"{LOCATION}/keyRings/kr2"


def test_duplicate_key_ring_conflicts() -> None:
    client = _client()
    client.create_key_ring(request={"parent": LOCATION, "key_ring_id": "kr"})
    with pytest.raises(gexc.Conflict):
        client.create_key_ring(request={"parent": LOCATION, "key_ring_id": "kr"})


def test_get_missing_key_not_found() -> None:
    with pytest.raises(gexc.NotFound):
        _client().get_crypto_key(
            request={"name": f"{LOCATION}/keyRings/kr/cryptoKeys/ghost"}
        )


def test_list_key_rings_and_keys() -> None:
    client = _client()
    _key(client, ring_id="kr", key_id="a")
    client.create_crypto_key(
        request={
            "parent": f"{LOCATION}/keyRings/kr",
            "crypto_key_id": "b",
            "crypto_key": {},
        }
    )

    rings = [
        r.name.rsplit("/", 1)[-1]
        for r in client.list_key_rings(request={"parent": LOCATION})
    ]
    assert rings == ["kr"]
    keys = sorted(
        k.name.rsplit("/", 1)[-1]
        for k in client.list_crypto_keys(request={"parent": f"{LOCATION}/keyRings/kr"})
    )
    assert keys == ["a", "b"]


# -- encrypt / decrypt ------------------------------------------------------


def test_encrypt_decrypt_round_trip() -> None:
    client = _client()
    key = _key(client)
    enc = client.encrypt(request={"name": key.name, "plaintext": b"top secret"})
    assert enc.ciphertext
    assert enc.verified_plaintext_crc32c is True
    dec = client.decrypt(request={"name": key.name, "ciphertext": enc.ciphertext})
    assert dec.plaintext == b"top secret"


def test_encrypt_decrypt_with_aad() -> None:
    client = _client()
    key = _key(client)
    enc = client.encrypt(
        request={
            "name": key.name,
            "plaintext": b"payload",
            "additional_authenticated_data": b"context",
        }
    )
    dec = client.decrypt(
        request={
            "name": key.name,
            "ciphertext": enc.ciphertext,
            "additional_authenticated_data": b"context",
        }
    )
    assert dec.plaintext == b"payload"


def test_decrypt_with_wrong_aad_fails() -> None:
    client = _client()
    key = _key(client)
    enc = client.encrypt(
        request={
            "name": key.name,
            "plaintext": b"payload",
            "additional_authenticated_data": b"context",
        }
    )
    with pytest.raises(gexc.GoogleAPICallError):
        client.decrypt(
            request={
                "name": key.name,
                "ciphertext": enc.ciphertext,
                "additional_authenticated_data": b"WRONG",
            }
        )


def test_backend_is_inspectable() -> None:
    client = _client()
    _key(client)
    assert f"{LOCATION}/keyRings/kr" in get_backend("kms")["test-project"].key_rings
