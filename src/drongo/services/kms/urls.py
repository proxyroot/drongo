"""URL routing table for Cloud KMS (moto-style ``url_bases``/``url_paths``)."""

from __future__ import annotations

from drongo.services.kms.responses import KMSResponse

_LOC = r"/v1/projects/(?P<project>[^/]+)/locations/(?P<location>[^/]+)"
_KR = _LOC + r"/keyRings/(?P<keyring>[^/]+)"
_CK = _KR + r"/cryptoKeys/(?P<cryptokey>[^/:]+)"

url_bases = [r"https?://cloudkms\.googleapis\.com"]

url_paths = {
    # Crypto operations (most specific first).
    f"POST {_CK}:encrypt": KMSResponse.encrypt,
    f"POST {_CK}:decrypt": KMSResponse.decrypt,
    # Crypto keys.
    f"POST {_KR}/cryptoKeys": KMSResponse.create_crypto_key,
    f"GET {_KR}/cryptoKeys": KMSResponse.list_crypto_keys,
    f"GET {_CK}": KMSResponse.get_crypto_key,
    # Key rings.
    f"POST {_LOC}/keyRings": KMSResponse.create_key_ring,
    f"GET {_LOC}/keyRings": KMSResponse.list_key_rings,
    f"GET {_KR}": KMSResponse.get_key_ring,
}
