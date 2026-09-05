#!/usr/bin/env python3
"""Verify every firmware image, optionally against the requested device profiles."""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def image_name(name):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*\.img\.gz", name):
        raise ValueError(f"Unsafe or invalid image name: {name!r}")
    return name


def verify_firmware(directory, expected_count=None, config=None, profile="standard"):
    directory = Path(directory)
    manifest = directory / "FIRMWARE_SHA256SUMS"
    if manifest.is_symlink() or not manifest.is_file():
        raise ValueError("Missing regular FIRMWARE_SHA256SUMS file")
    checksums = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-fA-F]{64}) [ *](.+)", line)
        if not match:
            raise ValueError(f"Invalid checksum entry: {line!r}")
        digest, name = match.groups()
        image_name(name)
        if name in checksums:
            raise ValueError(f"Duplicate checksum entry: {name}")
        checksums[name] = digest.lower()

    images = {p.name: p for p in directory.glob("*.img.gz")}
    if not images:
        raise ValueError("No firmware images found")
    if any(p.is_symlink() or not p.is_file() for p in images.values()):
        raise ValueError("Images must be regular files, not symlinks or directories")
    if set(images) != set(checksums):
        missing = sorted(set(images) - set(checksums))
        extra = sorted(set(checksums) - set(images))
        raise ValueError(f"Checksum coverage mismatch: missing={missing}, extra={extra}")
    if expected_count is not None and (expected_count < 1 or len(images) != expected_count):
        raise ValueError(f"Expected {expected_count} images, found {len(images)}")

    if config is not None:
        devices = re.findall(
            r"^CONFIG_TARGET_DEVICE_rockchip_armv8_DEVICE_(.+)=y$",
            Path(config).read_text(encoding="utf-8"), re.MULTILINE,
        )
        if not devices or len(devices) != len(set(devices)):
            raise ValueError("Requested device list is empty or duplicated")
        metadata = json.loads((directory / "profiles.json").read_text(encoding="utf-8"))
        if metadata.get("target") != "rockchip/armv8":
            raise ValueError("Unexpected profiles.json target")
        if profile not in ("standard", "docker"):
            raise ValueError(f"Unknown build profile: {profile}")
        prefix = "docker-" if profile == "docker" else ""
        expected = {}
        for device in devices:
            entries = metadata.get("profiles", {}).get(device, {}).get("images", [])
            entries = [entry for entry in entries if entry.get("name", "").endswith(".img.gz")]
            if not entries:
                raise ValueError(f"No image metadata for requested device: {device}")
            for entry in entries:
                name = prefix + image_name(entry["name"])
                if name in expected:
                    raise ValueError(f"Duplicate device image metadata: {name}")
                expected[name] = entry
        if set(images) != set(expected):
            raise ValueError(
                f"Device image mismatch: missing={sorted(set(expected) - set(images))}, "
                f"extra={sorted(set(images) - set(expected))}"
            )
        for name, entry in expected.items():
            if entry.get("sha256") != checksums[name] or entry.get("size") != images[name].stat().st_size:
                raise ValueError(f"Image metadata mismatch: {name}")

    for name, path in sorted(images.items()):
        if sha256(path) != checksums[name]:
            raise ValueError(f"SHA256 mismatch: {name}")
    return len(images)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--expected-count", type=int)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--profile", choices=("standard", "docker"), default="standard")
    args = parser.parse_args()
    try:
        count = verify_firmware(args.directory, args.expected_count, args.config, args.profile)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Firmware verification failed: {error}", file=sys.stderr)
        return 1
    print(f"Verified {count} firmware images (exact checksum coverage).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
