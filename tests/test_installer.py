import json

import pytest

from hexdeck import ed25519
from hexdeck.installer import InstallError, parse_manifest, target_name, verify_signature

# RFC 8032 section 7.1, tests 1-3.
RFC_VECTORS = [
    ("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
     "",
     "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
    ("3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
     "72",
     "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"),
    ("fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025",
     "af82",
     "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a"),
]


@pytest.mark.parametrize("key,message,signature", RFC_VECTORS)
def test_ed25519_accepts_rfc_vectors(key, message, signature):
    assert ed25519.verify(bytes.fromhex(key), bytes.fromhex(message), bytes.fromhex(signature))


@pytest.mark.parametrize("key,message,signature", RFC_VECTORS)
def test_ed25519_rejects_tampering(key, message, signature):
    tampered_message = bytes.fromhex(message) + b"x"
    assert not ed25519.verify(bytes.fromhex(key), tampered_message, bytes.fromhex(signature))
    flipped = bytearray(bytes.fromhex(signature))
    flipped[5] ^= 1
    assert not ed25519.verify(bytes.fromhex(key), bytes.fromhex(message), bytes(flipped))


def test_hex_signing_key_parses():
    from hexdeck.installer import SIGNING_KEY
    import base64
    assert len(ed25519.public_key_from_spki(base64.b64decode(SIGNING_KEY))) == 32


def test_signature_over_a_wrong_checksum_fails():
    assert not verify_signature("0" * 64, bytes(64))


def manifest(**overrides):
    sha = "a" * 64
    value = {
        "schema": 1, "app": "hex", "artifact": "desktop", "channel": "stable",
        "release": {"version": "3.4.0", "targets": {
            "linux-x64": {"url": f"/release/hex/files/{sha}/hex-linux-x64", "size": 1000, "sha256": sha},
            "linux-x64-sig": {"url": f"/release/hex/files/{'b' * 64}/hex.sig", "size": 64, "sha256": "b" * 64},
        }},
    }
    value.update(overrides)
    return json.dumps(value)


def test_parse_manifest():
    release = parse_manifest(manifest(), "stable", "linux-x64")
    assert release.version == "3.4.0"
    assert release.size == 1000
    assert release.signature_url.endswith("/hex.sig")


def test_manifest_for_another_channel_is_refused():
    with pytest.raises(InstallError):
        parse_manifest(manifest(), "dev", "linux-x64")


def test_manifest_with_an_unexpected_url_is_refused():
    bad = json.loads(manifest())
    bad["release"]["targets"]["linux-x64"]["url"] = "https://evil.example/hex"
    with pytest.raises(InstallError):
        parse_manifest(json.dumps(bad), "stable", "linux-x64")


def test_manifest_without_the_target_is_refused():
    with pytest.raises(InstallError):
        parse_manifest(manifest(), "stable", "linux-arm64")


def test_target_name():
    assert target_name("x86_64") == "linux-x64"
    assert target_name("aarch64") == "linux-arm64"
    with pytest.raises(InstallError):
        target_name("riscv64")
