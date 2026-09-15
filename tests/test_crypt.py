from __future__ import annotations

from pathlib import Path

import pytest

from noqte.crypt import (
    PassphraseSession,
    archive_dir_to_memory,
    decrypt_data,
    decrypt_file_with_retry,
    encrypt_data,
    is_tar_archive,
)


def test_encrypt_and_decrypt_bytes():
    payload = b"secret-api-key-12345"
    passphrase = "super-secure-password"

    ciphertext = encrypt_data(payload, passphrase)
    assert ciphertext != payload

    decrypted = decrypt_data(ciphertext, passphrase)
    assert decrypted == payload


def test_decrypt_invalid_passphrase_raises():
    payload = b"classified-content"
    ciphertext = encrypt_data(payload, "correct-pass")

    with pytest.raises(Exception):  # noqa: B017
        decrypt_data(ciphertext, "wrong-pass")


def test_archive_dir_to_memory_roundtrip(tmp_path: Path):
    source_dir = tmp_path / "secrets"
    source_dir.mkdir()
    (source_dir / "key.txt").write_text("my-private-key", encoding="utf-8")
    (source_dir / "sub").mkdir()
    (source_dir / "sub" / "token.json").write_text('{"token": "xyz"}', encoding="utf-8")

    tar_bytes = archive_dir_to_memory(source_dir)
    assert is_tar_archive(tar_bytes) is True
    assert is_tar_archive(b"plain-random-bytes-not-a-tar") is False

    ciphertext = encrypt_data(tar_bytes, "dir-pass")
    decrypted = decrypt_data(ciphertext, "dir-pass")
    assert is_tar_archive(decrypted) is True


def test_passphrase_session_caching_and_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("NOQTE_PASSPHRASE", "env-secret-token")
    session = PassphraseSession()

    assert session.get_decryption_passphrase() == "env-secret-token"
    assert session.get_encryption_passphrase() == "env-secret-token"


def test_decrypt_file_with_retry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("NOQTE_PASSPHRASE", "file-secret-pass")
    enc_file = tmp_path / "secret.encrypted"
    ciphertext = encrypt_data(b"top-secret-payload", "file-secret-pass")
    enc_file.write_bytes(ciphertext)

    session = PassphraseSession()
    decrypted = decrypt_file_with_retry(enc_file, session)
    assert decrypted == b"top-secret-payload"
