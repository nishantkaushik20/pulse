import base64
import json
import logging

from tests.gmail_app import TEST_KEY

from pulse_api.crypto import TokenCipherError, decrypt_token, encrypt_token
from pulse_api.logging import JsonFormatter


def test_encrypt_decrypt_round_trip() -> None:
    payload = encrypt_token(TEST_KEY, "refresh-token-PLAINTEXT-MARKER")

    assert decrypt_token(TEST_KEY, payload) == "refresh-token-PLAINTEXT-MARKER"
    assert b"refresh-token-PLAINTEXT-MARKER" not in payload


def test_wrong_key_fails() -> None:
    other = base64.b64encode(b"abcdefghijklmnopqrstuvwxyz012345").decode()
    payload = encrypt_token(TEST_KEY, "refresh-token-PLAINTEXT-MARKER")

    try:
        decrypt_token(other, payload)
    except TokenCipherError as exc:
        assert "refresh-token-PLAINTEXT-MARKER" not in str(exc)
    else:
        raise AssertionError("wrong key decrypted")


def test_malformed_ciphertext_fails() -> None:
    try:
        decrypt_token(TEST_KEY, b"short")
    except TokenCipherError as exc:
        assert "INTEGRATION" not in str(exc)
    else:
        raise AssertionError("malformed ciphertext decrypted")


def test_plaintext_and_encryption_key_are_redacted() -> None:
    record = logging.LogRecord(
        name="pulse_api.crypto",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="stored credential",
        args=(),
        exc_info=None,
    )
    record.access_token = "access-token-value"
    record.refresh_token = "refresh-token-PLAINTEXT-MARKER"
    record.integration_encryption_key = TEST_KEY
    record.safe = "visible"

    payload = json.loads(JsonFormatter().format(record))
    serialized = json.dumps(payload)

    assert "access-token-value" not in serialized
    assert "refresh-token-PLAINTEXT-MARKER" not in serialized
    assert TEST_KEY not in serialized
    assert payload["safe"] == "visible"
    assert payload["access_token"] == "***"
    assert payload["integration_encryption_key"] == "***"
