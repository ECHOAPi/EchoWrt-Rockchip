#!/usr/bin/env python3
"""Upload a verified firmware set to a draft, then publish it without overwriting releases."""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from firmware import sha256, verify_firmware


def gh(*args):
    return subprocess.run(["gh", *args], check=True, text=True, capture_output=True).stdout


def api(endpoint):
    return json.loads(gh("api", endpoint))


def collection(endpoint):
    pages = json.loads(gh("api", endpoint, "--paginate", "--slurp"))
    return [item for page in pages for item in page]


def release_for_tag(repo, tag):
    matches = [r for r in collection(f"repos/{repo}/releases?per_page=100") if r["tag_name"] == tag]
    if len(matches) > 1:
        raise ValueError(f"Multiple releases use tag {tag}; resolve them manually")
    return matches[0] if matches else None


def verify_tag(repo, tag, source_sha):
    refs = api(f"repos/{repo}/git/matching-refs/tags/{tag}")
    refs = [ref for ref in refs if ref["ref"] == f"refs/tags/{tag}"]
    if not refs:
        return
    obj = refs[0]["object"]
    for _ in range(8):
        if obj["type"] != "tag":
            break
        obj = api(f"repos/{repo}/git/tags/{obj['sha']}")["object"]
    if obj["type"] != "commit" or obj["sha"] != source_sha:
        raise ValueError(f"Existing tag {tag} does not point to source commit {source_sha}")


def verify_draft(release, source_sha):
    if not release["draft"]:
        raise ValueError("Release is already public; use a new tag, never overwrite published assets")
    if release["target_commitish"] != source_sha:
        raise ValueError("Draft release target does not match the source commit")


def matching_assets(repo, release_id, expected, complete=False):
    assets = collection(f"repos/{repo}/releases/{release_id}/assets?per_page=100")
    seen = set()
    for asset in assets:
        name = asset["name"]
        if name in seen or name not in expected:
            raise ValueError(f"Unexpected or duplicate draft asset: {name}")
        seen.add(name)
        if (asset.get("state") != "uploaded" or asset.get("size") != expected[name]["size"]
                or asset.get("digest") != expected[name]["digest"]):
            raise ValueError(f"Draft asset does not match local size/SHA256: {name}")
    if complete and seen != set(expected):
        raise ValueError(f"Draft is incomplete: missing={sorted(set(expected) - seen)}")
    return seen


def publish(directory, repo, tag, title, source_sha, notes, expected_count=None,
            config=None, profile="standard"):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("Invalid repository name")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", tag):
        raise ValueError("Invalid release tag")
    if not re.fullmatch(r"[0-9a-f]{40}", source_sha):
        raise ValueError("Release target must be an exact source commit SHA")
    directory, notes = Path(directory), Path(notes)
    if not notes.is_file():
        raise ValueError("Missing release notes")
    count = verify_firmware(directory, expected_count, config, profile)
    files = sorted(directory.iterdir())
    if any(path.is_symlink() for path in files):
        raise ValueError("Release assets must not be symlinks")
    files = [path for path in files if path.is_file()]
    expected = {}
    # Check all files before creating a draft or uploading anything.
    for path in files:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", path.name):
            raise ValueError(f"Unsafe release asset name: {path.name}")
        size = path.stat().st_size
        if size >= 2 * 1024 ** 3:
            raise ValueError(f"Release asset must be smaller than 2 GiB: {path.name}")
        expected[path.name] = {"size": size, "digest": "sha256:" + sha256(path)}

    release = release_for_tag(repo, tag)
    if release:
        verify_draft(release, source_sha)
    verify_tag(repo, tag, source_sha)
    if release is None:
        gh("release", "create", tag, "--repo", repo, "--draft", "--target", source_sha,
           "--title", title, "--notes-file", str(notes))
        release = release_for_tag(repo, tag)
        if release is None:
            raise ValueError("Created draft is not yet visible; safely rerun to resume")
        verify_draft(release, source_sha)

    uploaded = matching_assets(repo, release["id"], expected)
    for path in files:
        if path.name not in uploaded:
            # No --clobber: a failed run leaves a draft; a rerun verifies and skips matching assets.
            gh("release", "upload", tag, str(path), "--repo", repo)
    matching_assets(repo, release["id"], expected, complete=True)
    current = release_for_tag(repo, tag)
    if current is None or current["id"] != release["id"]:
        raise ValueError("Draft changed during upload; refusing to publish")
    verify_draft(current, source_sha)
    verify_tag(repo, tag, source_sha)
    gh("release", "edit", tag, "--repo", repo, "--draft=false", "--latest",
       "--title", title, "--notes-file", str(notes))
    return count, current["html_url"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--notes", required=True, type=Path)
    parser.add_argument("--expected-count", type=int)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--profile", choices=("standard", "docker"), default="standard")
    args = parser.parse_args()
    try:
        count, url = publish(args.directory, args.repo, args.tag, args.title, args.source_sha,
                             args.notes, args.expected_count, args.config, args.profile)
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        print(f"Release publishing failed: {error}", file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError):
            print(error.stderr, file=sys.stderr)
        return 1
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
            output.write(f"release_url={url}\nimage_count={count}\n")
    print(f"Published {count} verified images: {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
