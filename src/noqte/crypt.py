from __future__ import annotations

import io
import os
import tarfile
from pathlib import Path

from pyrage import passphrase as age_passphrase  # pyright: ignore[reportAttributeAccessIssue]

from noqte.logger import console, log_error


def is_tar_archive(data: bytes) -> bool:
    """Check if raw in-memory bytes represent a valid tar archive."""
    try:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:*"):
            return True
    except (tarfile.TarError, EOFError, OSError):
        return False


def archive_dir_to_memory(
    src_dir: Path,
    allowed_paths: set[Path] | None = None,
) -> bytes:
    """Pack a directory subtree into an in-memory gzipped tar archive without touching disk."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for root, _, files in os.walk(src_dir, followlinks=False):
            root_path = Path(root)
            try:
                rel_root = root_path.relative_to(src_dir)
            except ValueError:
                rel_root = Path(".")

            for f in files:
                full_file = root_path / f
                if full_file.is_symlink():
                    continue

                rel_file = rel_root / f if rel_root != Path(".") else Path(f)
                if allowed_paths is not None and rel_file not in allowed_paths:
                    continue

                tar.add(full_file, arcname=str(rel_file), recursive=False)

    return buf.getvalue()


def encrypt_data(plaintext: bytes, passphrase_str: str) -> bytes:
    """Encrypt raw bytes using pyrage passphrase encryption."""
    return age_passphrase.encrypt(plaintext, passphrase_str)


def decrypt_data(ciphertext: bytes, passphrase_str: str) -> bytes:
    """Decrypt age-encrypted ciphertext using the provided passphrase."""
    return age_passphrase.decrypt(ciphertext, passphrase_str)


class PassphraseSession:
    """In-memory passphrase cache for the duration of a CLI command run."""

    def __init__(self) -> None:
        self._cached: str | None = None

    def get_encryption_passphrase(self) -> str:
        if self._cached:
            return self._cached

        env_val = os.environ.get("NOQTE_PASSPHRASE")
        if env_val:
            self._cached = env_val
            return self._cached

        console.print("\n[bold cyan]Encryption Passphrase Required[/bold cyan]")
        while True:
            p1 = console.input("[bold yellow]Enter passphrase: [/bold yellow]", password=True)
            if not p1:
                console.print("[red]Passphrase cannot be empty.[/red]")
                continue
            p2 = console.input("[bold yellow]Confirm passphrase: [/bold yellow]", password=True)
            if p1 != p2:
                console.print("[red]Passphrases do not match. Try again.[/red]")
                continue
            self._cached = p1
            return self._cached

    def get_decryption_passphrase(self, retry: bool = False) -> str:
        if retry:
            self._cached = None

        if self._cached:
            return self._cached

        env_val = os.environ.get("NOQTE_PASSPHRASE")
        if env_val and not retry:
            self._cached = env_val
            return self._cached

        console.print("\n[bold cyan]Decryption Passphrase Required[/bold cyan]")
        while True:
            p = console.input("[bold yellow]Enter passphrase: [/bold yellow]", password=True)
            if not p:
                console.print("[red]Passphrase cannot be empty.[/red]")
                continue
            self._cached = p
            return self._cached


def decrypt_file_with_retry(
    src_path: Path,
    session: PassphraseSession,
    max_retries: int = 3,
) -> bytes | None:
    """Read and decrypt an age file with interactive retry prompts on failure."""
    ciphertext = src_path.read_bytes()

    for attempt in range(max_retries):
        pwd = session.get_decryption_passphrase(retry=(attempt > 0))
        try:
            return decrypt_data(ciphertext, pwd)
        except Exception as e:
            log_error(f"Decryption failed for '{src_path.name}' (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                raise RuntimeError(f"Failed to decrypt '{src_path.name}' after {max_retries} attempts.") from e
