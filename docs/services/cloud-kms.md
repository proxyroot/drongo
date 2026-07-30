# Cloud KMS

- **Client:** `google-cloud-kms` (`kms.KeyManagementServiceClient`)
- **Transport:** gRPC (the client default), forced to **REST** during a mock scope.
- **Backend:** per-project.

Use the **normal** client with no `transport` argument.

!!! note "Reversible mock encryption"
    Real KMS never exposes key material, so drongo can't do real cryptography.
    Instead it uses a **reversible** encoding that embeds the key name and the
    additional authenticated data (AAD): `decrypt` returns the original plaintext
    only when the **same key and AAD** are used, and fails otherwise. That's
    enough to exercise envelope-encryption code paths in tests. Do not treat the
    ciphertext as secure. The crc32c integrity checks the client performs are
    honored, so encrypt/decrypt verify cleanly.

## Key rings and crypto keys

```python
from drongo import mock_gcp


@mock_gcp
def test_keys():
    from google.cloud import kms

    client = kms.KeyManagementServiceClient()
    location = "projects/my-project/locations/us-central1"

    ring = client.create_key_ring(request={"parent": location, "key_ring_id": "kr"})
    key = client.create_crypto_key(
        request={
            "parent": ring.name,
            "crypto_key_id": "app-key",
            "crypto_key": {"purpose": kms.CryptoKey.CryptoKeyPurpose.ENCRYPT_DECRYPT},
        }
    )
    assert key.primary.name.endswith("/cryptoKeyVersions/1")
```

## Encrypt and decrypt

```python
@mock_gcp
def test_encrypt_decrypt():
    from google.cloud import kms

    client = kms.KeyManagementServiceClient()
    key_name = "projects/p/locations/us-central1/keyRings/kr/cryptoKeys/app-key"

    enc = client.encrypt(request={"name": key_name, "plaintext": b"top secret"})
    dec = client.decrypt(request={"name": key_name, "ciphertext": enc.ciphertext})
    assert dec.plaintext == b"top secret"
```

Additional authenticated data (AAD) is enforced: decrypting with a different AAD
than was used to encrypt fails, just like real KMS.

## Coverage

| Operation | Status |
| --- | --- |
| Create / get / list key ring | Supported |
| Create / get / list crypto key | Supported |
| Encrypt / decrypt (with AAD) | Supported (reversible mock) |
| Crypto-key versions (create / list / destroy) | Planned |
| Asymmetric sign / verify, MAC, raw encrypt | Planned |
| Rotation, IAM policy, import jobs | Planned |
