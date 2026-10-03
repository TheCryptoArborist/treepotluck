"""Obtain only a pinned official Sui CLI. No wallet commands or transactions.

Downloads are opt-in. The tarball may exceed 1 GB on Linux. Only the single CLI
executable is extracted; archive paths and links are never trusted. Python 3.10+.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import tarfile
import tempfile
from urllib.request import Request, urlopen


class ToolchainError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def platform_key(system: str | None = None, machine: str | None = None) -> str:
    system = system or platform.system()
    machine = (machine or platform.machine()).lower()
    machine = {"amd64": "x86_64", "arm64": "aarch64"}.get(machine, machine)
    return f"{system}-{machine}"


def load_lock(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not re.fullmatch(r"mainnet-v\d+\.\d+\.\d+", data.get("tag", "")):
        raise ToolchainError("Expected a pinned mainnet release tag.")
    if data["tag"] != "mainnet-v" + data.get("version", ""):
        raise ToolchainError("Version and tag do not match.")
    if not re.fullmatch(r"[a-f0-9]{40}", data.get("commit", "")):
        raise ToolchainError("Missing source commit.")
    for asset in data["assets"].values():
        if not re.fullmatch(r"sui-mainnet-v[0-9.]+-[a-z0-9_-]+\.tgz", asset.get("name", "")):
            raise ToolchainError("Invalid archive name.")
        if not asset["name"].startswith("sui-" + data["tag"] + "-"):
            raise ToolchainError("Archive version mismatch.")
        if not re.fullmatch(r"[a-f0-9]{64}", asset.get("sha256", "")):
            raise ToolchainError("Missing valid archive checksum.")
        if type(asset.get("size")) is not int or not 0 < asset["size"] <= 2_000_000_000:
            raise ToolchainError("Invalid archive size.")
    return data


def archive_url(lock: dict, asset: dict) -> str:
    return f"https://github.com/MystenLabs/sui/releases/download/{lock['tag']}/{asset['name']}"


def verify_archive(path: Path, asset: dict) -> None:
    if path.stat().st_size != asset["size"]:
        raise ToolchainError("Archive length differs from the pinned release metadata.")
    if sha256_file(path) != asset["sha256"]:
        raise ToolchainError("Archive SHA256 mismatch; executable will not be installed.")


def extract_cli(archive: Path, destination: Path, executable: str) -> None:
    """Never extractall(). Only copy bytes of one regular-file CLI member."""
    with tarfile.open(archive, "r:gz") as tar:
        candidates = []
        for member in tar.getmembers():
            path = PurePosixPath(member.name)
            if path.name != executable:
                continue
            if path.is_absolute() or ".." in path.parts or "\\" in member.name:
                raise ToolchainError("Unsafe CLI path in archive.")
            if not member.isfile() or member.issym() or member.islnk():
                raise ToolchainError("CLI must be a regular file, not a link.")
            if not 0 < member.size <= 500_000_000:
                raise ToolchainError("CLI member size is outside the allowed range.")
            candidates.append(member)
        if len(candidates) != 1:
            raise ToolchainError("Expected exactly one CLI executable in the archive.")
        stream = tar.extractfile(candidates[0])
        if stream is None:
            raise ToolchainError("CLI archive member could not be read.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with stream, destination.open("wb") as output:
            shutil.copyfileobj(stream, output, 1024 * 1024)
        if destination.stat().st_size != candidates[0].size:
            destination.unlink(missing_ok=True)
            raise ToolchainError("CLI extraction was incomplete.")
    destination.chmod(0o755)


def install(root: Path, archive: Path | None = None) -> Path:
    lock = load_lock(root / "toolchain-lock.json")
    key = platform_key()
    if key not in lock["assets"]:
        raise ToolchainError(f"No pinned archive for {key}.")
    asset = lock["assets"][key]
    executable = "sui.exe" if key.startswith("Windows-") else "sui"
    target_dir = root / ".tools" / lock["tag"] / key
    target_dir.mkdir(parents=True, exist_ok=True)
    destination = target_dir / executable
    receipt = target_dir / "installation.json"
    if archive is None and destination.is_file() and receipt.is_file():
        cached = json.loads(receipt.read_text(encoding="utf-8"))
        if (cached.get("archive_sha256") == asset["sha256"]
                and cached.get("binary_sha256") == sha256_file(destination)):
            return destination
        raise ToolchainError("Cached CLI failed integrity check; remove its .tools directory and retry.")
    with tempfile.TemporaryDirectory(prefix="sui-install-", dir=target_dir) as temporary:
        work = Path(temporary)
        downloaded = archive or work / asset["name"]
        if archive is None:
            url = archive_url(lock, asset)
            request = Request(url, headers={"User-Agent": "TREE-Pot-local-validation/2"})
            try:
                total = 0
                with urlopen(request, timeout=60) as response, downloaded.open("wb") as output:
                    if not response.geturl().startswith("https://"):
                        raise ToolchainError("Refusing a non-HTTPS download redirect.")
                    while chunk := response.read(1024 * 1024):
                        total += len(chunk)
                        if total > asset["size"]:
                            raise ToolchainError("Download exceeds pinned size.")
                        output.write(chunk)
            except OSError as exc:
                raise ToolchainError(f"Official compiler download failed: {exc}") from exc
        verify_archive(downloaded, asset)
        staged = work / executable
        extract_cli(downloaded, staged, executable)
        binary_hash = sha256_file(staged)
        os.replace(staged, destination)
        receipt.write_text(json.dumps({"tag": lock["tag"], "platform": key,
            "archive_sha256": asset["sha256"], "binary_sha256": binary_hash,
            "source_url": archive_url(lock, asset)}, indent=2) + "\n", encoding="utf-8")
    return destination
