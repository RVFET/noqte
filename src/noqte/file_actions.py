from __future__ import annotations

import io
import os
import shutil
import subprocess
import tarfile
import tempfile
from collections.abc import Callable
from pathlib import Path

from wcmatch import glob

from noqte.config import DotfileTarget
from noqte.crypt import (
    PassphraseSession,
    archive_dir_to_memory,
    decrypt_file_with_retry,
    encrypt_data,
    is_tar_archive,
)
from noqte.logger import log_error, log_info, log_warn, logger

GLOB_FLAGS = glob.GLOBSTAR | glob.EXTGLOB | glob.BRACE | glob.DOTGLOB


def get_repo_target_path(configs_dir: Path, entry: DotfileTarget) -> Path:
    filename = f"{entry.name}.encrypted" if entry.encrypted else entry.name
    return configs_dir / filename


def is_symlink_safeguard(path: Path, label: str) -> bool:
    if path.is_symlink():
        log_warn(f"Skipping {label} '{path}': Symlinks are ignored by safety policy.")
        return True
    return False


def safe_copy_file(
    src: Path,
    dest: Path,
    temporarily_own: bool = True,
    dry_run: bool = False,
) -> None:
    if dry_run:
        log_info(f"[DRY-RUN] copy {src} -> {dest}")
        return

    original_mode: int | None = None
    perm_unlocked = False

    if dest.exists() and not dest.is_symlink():
        try:
            st = dest.stat()
            original_mode = st.st_mode
            if not os.access(dest, os.W_OK):
                if not temporarily_own:
                    log_warn(f"Skipping write-protected file '{dest}' (temporarily_own=False).")
                    return
                dest.chmod(original_mode | 0o200)
                perm_unlocked = True
        except Exception as e:
            log_warn(f"Permission inspection failed for '{dest}': {e}")

    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        logger.info(f"    [FILE COPIED] {src} -> {dest}")
    finally:
        if original_mode is not None and perm_unlocked and dest.exists():
            try:
                dest.chmod(original_mode)
            except Exception as e:
                log_warn(f"Failed to restore original mode on '{dest}': {e}")


def is_pattern_matched(rel_path_str: str, patterns: list[str]) -> bool:
    formatted: list[str] = []
    for p in patterns:
        clean = p.rstrip("/")
        formatted.append(p)
        if p.endswith("/"):
            formatted.append(f"{clean}/**")
    return glob.globmatch(rel_path_str, formatted, flags=GLOB_FLAGS)


def build_allowed_paths(
    src_dir: Path,
    exclude_patterns: list[str] | None,
    include_patterns: list[str] | None,
) -> set[Path] | None:
    if not exclude_patterns and not include_patterns:
        return None

    allowed: set[Path] = set()
    for root, _, files in os.walk(src_dir, followlinks=False):
        root_path = Path(root)
        try:
            rel_root = root_path.relative_to(src_dir)
        except ValueError:
            rel_root = Path(".")

        for f in files:
            full_path = root_path / f
            if full_path.is_symlink():
                log_warn(f"Skipping symlink inside tree: '{full_path}'")
                continue

            rel_file = rel_root / f if rel_root != Path(".") else Path(f)
            rel_str = rel_file.as_posix()

            if exclude_patterns and is_pattern_matched(rel_str, exclude_patterns):
                continue
            if include_patterns and not is_pattern_matched(rel_str, include_patterns):
                continue

            allowed.add(rel_file)
            curr = rel_file.parent
            while curr != Path("."):
                allowed.add(curr)
                curr = curr.parent

    return allowed


def create_ignore_callback(src_dir: Path, allowed_paths: set[Path] | None) -> Callable[[str, list[str]], set[str]] | None:
    if allowed_paths is None:
        return None

    def ignore_callback(dir_path: str, names: list[str]) -> set[str]:
        ignored: set[str] = set()
        try:
            rel_dir = Path(dir_path).relative_to(src_dir)
        except ValueError:
            rel_dir = Path(".")

        for name in names:
            rel_path = rel_dir / name if rel_dir != Path(".") else Path(name)
            if rel_path not in allowed_paths:
                ignored.add(name)
        return ignored

    return ignore_callback


def transfer_path(
    src: Path,
    dest: Path,
    overwrite: bool = False,
    exclude: list[str] | None = None,
    include: list[str] | None = None,
    temporarily_own: bool = True,
    dry_run: bool = False,
) -> bool:
    if is_symlink_safeguard(src, "source") or is_symlink_safeguard(dest, "destination"):
        return False

    if dry_run:
        log_info(f"[DRY-RUN] transfer {src} -> {dest}")
        return True

    def copy_func(s: str | Path, d: str | Path) -> None:
        safe_copy_file(Path(s), Path(d), temporarily_own=temporarily_own, dry_run=dry_run)

    try:
        if dest.exists():
            if dest.is_file():
                copy_func(src, dest)
                return True
            if dest.is_dir() and overwrite:
                shutil.rmtree(dest)

        dest.parent.mkdir(parents=True, exist_ok=True)

        if src.is_dir():
            allowed = build_allowed_paths(src, exclude, include)
            ignore_func = create_ignore_callback(src, allowed)
            shutil.copytree(
                src,
                dest,
                symlinks=False,
                ignore=ignore_func,
                copy_function=copy_func,
                dirs_exist_ok=True,
            )
        else:
            copy_func(src, dest)
        return True

    except PermissionError:
        log_warn(f"Permission denied on '{dest}'. Executing elevated staging transfer via sudo...")
        try:
            with tempfile.TemporaryDirectory(prefix="noqte_stage_") as stage_tmp:
                stage_dir = Path(stage_tmp)
                if src.is_dir():
                    allowed = build_allowed_paths(src, exclude, include)
                    ignore_func = create_ignore_callback(src, allowed)
                    shutil.copytree(
                        src,
                        stage_dir / "payload",
                        symlinks=False,
                        ignore=ignore_func,
                        copy_function=copy_func,
                        dirs_exist_ok=True,
                    )
                else:
                    (stage_dir / "payload").parent.mkdir(parents=True, exist_ok=True)
                    copy_func(src, stage_dir / "payload" / src.name)

                subprocess.run(["sudo", "mkdir", "-p", str(dest.parent)], check=True)
                if overwrite and dest.exists() and dest.is_dir():
                    subprocess.run(["sudo", "rm", "-rf", str(dest)], check=True)

                if src.is_dir():
                    subprocess.run(["sudo", "cp", "-a", "-T", str(stage_dir / "payload"), str(dest)], check=True)
                else:
                    subprocess.run(["sudo", "cp", "-a", str(stage_dir / "payload" / src.name), str(dest)], check=True)
                return True
        except subprocess.SubprocessError as e:
            log_error(f"Elevated transfer failed for '{dest}': {e}")
            return False
    except Exception as e:
        log_error(f"Transfer error ({src} -> {dest}): {e}")
        return False


def write_secure_bytes(
    dest: Path,
    data: bytes,
    temporarily_own: bool = True,
    dry_run: bool = False,
) -> bool:
    if is_symlink_safeguard(dest, "destination"):
        return False

    if dry_run:
        log_info(f"[DRY-RUN] write secure bytes -> {dest} ({len(data)} bytes)")
        return True

    original_mode: int | None = None
    perm_unlocked = False

    if dest.exists() and not dest.is_symlink():
        try:
            st = dest.stat()
            original_mode = st.st_mode
            if not os.access(dest, os.W_OK):
                if not temporarily_own:
                    log_warn(f"Skipping write-protected file '{dest}' (temporarily_own=False).")
                    return False
                dest.chmod(original_mode | 0o200)
                perm_unlocked = True
        except Exception as e:
            log_warn(f"Permission inspection failed for '{dest}': {e}")

    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        logger.info(f"    [FILE WRITTEN] -> {dest}")
        return True
    except PermissionError:
        log_warn(f"Permission denied on '{dest}'. Executing elevated staging transfer via sudo...")
        try:
            with tempfile.TemporaryDirectory(prefix="noqte_stage_") as stage_tmp:
                temp_file = Path(stage_tmp) / dest.name
                temp_file.write_bytes(data)
                subprocess.run(["sudo", "mkdir", "-p", str(dest.parent)], check=True)
                subprocess.run(["sudo", "cp", "-a", str(temp_file), str(dest)], check=True)
                return True
        except subprocess.SubprocessError as e:
            log_error(f"Elevated write failed for '{dest}': {e}")
            return False
    except Exception as e:
        log_error(f"Write error for '{dest}': {e}")
        return False
    finally:
        if original_mode is not None and perm_unlocked and dest.exists():
            try:
                dest.chmod(original_mode)
            except Exception as e:
                log_warn(f"Failed to restore original mode on '{dest}': {e}")


def extract_tar_bytes(
    tar_bytes: bytes,
    dest_dir: Path,
    overwrite: bool = False,
    dry_run: bool = False,
) -> bool:
    if is_symlink_safeguard(dest_dir, "destination"):
        return False

    if dry_run:
        try:
            with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:*") as tar:
                count = len(tar.getnames())
            log_info(f"[DRY-RUN] extract encrypted tarball -> {dest_dir} ({count} entries)")
        except Exception:
            log_info(f"[DRY-RUN] extract encrypted tarball -> {dest_dir}")
        return True

    if dest_dir.exists():
        if dest_dir.is_file():
            dest_dir.unlink()
        elif dest_dir.is_dir() and overwrite:
            shutil.rmtree(dest_dir)

    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:*") as tar:
            tar.extractall(dest_dir, filter="data")
        logger.info(f"    [TAR EXTRACTED] -> {dest_dir}")
        return True
    except PermissionError:
        log_warn(f"Permission denied on '{dest_dir}'. Executing elevated tar staging via sudo...")
        try:
            with tempfile.TemporaryDirectory(prefix="noqte_stage_tar_") as stage_tmp:
                stage_dir = Path(stage_tmp)
                with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:*") as tar:
                    tar.extractall(stage_dir, filter="data")
                subprocess.run(["sudo", "mkdir", "-p", str(dest_dir)], check=True)
                if overwrite and dest_dir.exists() and dest_dir.is_dir():
                    subprocess.run(["sudo", "rm", "-rf", str(dest_dir)], check=True)
                subprocess.run(["sudo", "cp", "-a", "-T", str(stage_dir), str(dest_dir)], check=True)
                return True
        except subprocess.SubprocessError as e:
            log_error(f"Elevated tar extraction failed for '{dest_dir}': {e}")
            return False
    except Exception as e:
        log_error(f"Tar extraction error for '{dest_dir}': {e}")
        return False


def prune_empty_directories(base_dir: Path, dry_run: bool = False) -> list[Path]:
    if not base_dir.exists() or not base_dir.is_dir():
        return []

    pruned: list[Path] = []
    for root, _, _ in os.walk(base_dir, topdown=False):
        root_path = Path(root)
        if root_path == base_dir:
            continue

        try:
            if not any(root_path.iterdir()):
                pruned.append(root_path)
                if not dry_run:
                    root_path.rmdir()
        except (OSError, PermissionError):
            pass

    return pruned


def collect_target(
    entry: DotfileTarget,
    configs_dir: Path,
    session: PassphraseSession,
    dry_run: bool = False,
) -> bool:
    host_src = entry.resolve_destination()
    repo_dest = get_repo_target_path(configs_dir, entry)

    if not host_src.exists():
        log_warn(f"Skipping '{entry.name}': Host path '{host_src}' missing.")
        return False

    if entry.encrypted:
        passphrase = None if dry_run else session.get_encryption_passphrase()

        if host_src.is_dir():
            if dry_run:
                log_info(f"[DRY-RUN] encrypt directory & collect: '{entry.name}' <- {host_src}")
                return True

            try:
                allowed = build_allowed_paths(host_src, entry.exclude, entry.include)
                tar_bytes = archive_dir_to_memory(host_src, allowed)
                ciphertext = encrypt_data(tar_bytes, passphrase)

                if write_secure_bytes(
                    repo_dest,
                    ciphertext,
                    temporarily_own=entry.temporarily_own,
                    dry_run=dry_run,
                ):
                    log_info(f"Encrypted Directory & Collected: '{entry.name}' <- {host_src}")
                    return True
            except Exception as e:
                log_error(f"Failed to encrypt directory '{entry.name}': {e}")
                return False
        else:
            if dry_run:
                log_info(f"[DRY-RUN] encrypt file & collect: '{entry.name}' <- {host_src}")
                return True

            try:
                plaintext_bytes = host_src.read_bytes()
                ciphertext = encrypt_data(plaintext_bytes, passphrase)

                if write_secure_bytes(
                    repo_dest,
                    ciphertext,
                    temporarily_own=entry.temporarily_own,
                    dry_run=dry_run,
                ):
                    log_info(f"Encrypted File & Collected: '{entry.name}' <- {host_src}")
                    return True
            except Exception as e:
                log_error(f"Failed to encrypt file '{entry.name}': {e}")
                return False
        return False

    if transfer_path(
        host_src,
        repo_dest,
        overwrite=entry.overwrite,
        exclude=entry.exclude,
        include=entry.include,
        temporarily_own=entry.temporarily_own,
        dry_run=dry_run,
    ):
        log_info(f"Collected: '{entry.name}' <- {host_src}")
        return True
    return False


def deploy_target(
    entry: DotfileTarget,
    configs_dir: Path,
    session: PassphraseSession,
    dry_run: bool = False,
) -> bool:
    repo_src = get_repo_target_path(configs_dir, entry)
    host_dest = entry.resolve_destination()

    if not repo_src.exists():
        log_warn(f"Skipping '{entry.name}': Not found in repository at '{repo_src}'.")
        return False

    if entry.encrypted:
        if dry_run:
            log_info(f"[DRY-RUN] decrypt & deploy: '{entry.name}' -> {host_dest}")
            return True

        try:
            decrypted_bytes = decrypt_file_with_retry(repo_src, session)

            if is_tar_archive(decrypted_bytes):
                if extract_tar_bytes(
                    decrypted_bytes,
                    host_dest,
                    overwrite=entry.overwrite,
                    dry_run=dry_run,
                ):
                    log_info(f"Decrypted Directory & Deployed: '{entry.name}' -> {host_dest}")
                    return True
            else:
                if write_secure_bytes(
                    host_dest,
                    decrypted_bytes,
                    temporarily_own=entry.temporarily_own,
                    dry_run=dry_run,
                ):
                    log_info(f"Decrypted File & Deployed: '{entry.name}' -> {host_dest}")
                    return True
        except Exception as e:
            log_error(f"Failed to deploy encrypted entry '{entry.name}': {e}")
            return False
        return False

    if transfer_path(
        repo_src,
        host_dest,
        overwrite=entry.overwrite,
        exclude=entry.exclude,
        include=entry.include,
        temporarily_own=entry.temporarily_own,
        dry_run=dry_run,
    ):
        log_info(f"Deployed: '{entry.name}' -> {host_dest}")
        return True
    return False
