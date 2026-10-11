import pytest

from app.core import crypto


def test_encrypt_round_trip() -> None:
    encrypted = crypto.encrypt("ya29.secret-token")

    assert "ya29" not in encrypted
    assert crypto.decrypt(encrypted) == "ya29.secret-token"


def test_encrypt_uses_a_fresh_nonce() -> None:
    assert crypto.encrypt("same") != crypto.encrypt("same")


def test_decrypt_rejects_tampered_data() -> None:
    encrypted = crypto.encrypt("secret")
    tampered = ("A" if encrypted[-5] != "A" else "B").join([encrypted[:-5], encrypted[-4:]])

    with pytest.raises(crypto.DecryptionError):
        crypto.decrypt(tampered)


def test_decrypt_rejects_garbage() -> None:
    with pytest.raises(crypto.DecryptionError):
        crypto.decrypt("not-base64!!")
