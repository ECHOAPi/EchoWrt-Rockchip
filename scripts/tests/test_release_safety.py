import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))
import firmware

spec = importlib.util.spec_from_file_location("publisher", SCRIPTS / "publish-firmware.py")
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)
SOURCE_SHA = "a" * 40


class FirmwareFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="release-test-", dir=Path(__file__).parent)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.directory = self.root / "firmware"
        self.directory.mkdir()
        self.entries = {}
        for name, data in (("a.img.gz", b"image A"), ("b.img.gz", b"image B")):
            (self.directory / name).write_bytes(data)
            self.entries[name] = hashlib.sha256(data).hexdigest()
        self.manifest = self.directory / "FIRMWARE_SHA256SUMS"
        self.write_manifest()
        self.config = self.root / "requested.config"
        self.config.write_text("CONFIG_TARGET_DEVICE_rockchip_armv8_DEVICE_board-a=y\n"
                               "CONFIG_TARGET_DEVICE_rockchip_armv8_DEVICE_board-b=y\n")
        self.metadata = {"target": "rockchip/armv8", "profiles": {}}
        for device, name in (("board-a", "a.img.gz"), ("board-b", "b.img.gz")):
            self.metadata["profiles"][device] = {"images": [{"name": name,
                "sha256": self.entries[name], "size": (self.directory / name).stat().st_size}]}
        self.write_metadata()
        self.notes = self.root / "notes.md"
        self.notes.write_text("Fixture release notes\n")

    def write_manifest(self):
        self.manifest.write_text("".join(f"{digest}  {name}\n" for name, digest in self.entries.items()))

    def write_metadata(self):
        (self.directory / "profiles.json").write_text(json.dumps(self.metadata))


class FirmwareTests(FirmwareFixture):
    def test_valid_complete_set(self):
        self.assertEqual(firmware.verify_firmware(self.directory, 2, self.config), 2)

    def test_duplicate_checksum_cannot_hide_unverified_image(self):
        self.manifest.write_text(f"{self.entries['a.img.gz']}  a.img.gz\n" * 2)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            firmware.verify_firmware(self.directory, 2)

    def test_missing_checksum(self):
        self.entries.pop("b.img.gz")
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, "coverage mismatch"):
            firmware.verify_firmware(self.directory)

    def test_checksum_for_missing_file(self):
        (self.directory / "b.img.gz").unlink()
        with self.assertRaisesRegex(ValueError, "coverage mismatch"):
            firmware.verify_firmware(self.directory)

    def test_corrupt_image(self):
        (self.directory / "a.img.gz").write_bytes(b"corrupted")
        with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
            firmware.verify_firmware(self.directory)

    def test_unsafe_names(self):
        for name in ("../a.img.gz", "/a.img.gz", "sub/a.img.gz", "-a.img.gz"):
            with self.subTest(name=name):
                self.manifest.write_text(f"{self.entries['a.img.gz']}  {name}\n")
                with self.assertRaisesRegex(ValueError, "Unsafe"):
                    firmware.verify_firmware(self.directory)

    def test_malformed_manifest(self):
        self.manifest.write_text("not a checksum\n")
        with self.assertRaisesRegex(ValueError, "Invalid checksum"):
            firmware.verify_firmware(self.directory)

    def test_symlink_image(self):
        (self.directory / "a.img.gz").unlink()
        (self.directory / "a.img.gz").symlink_to("b.img.gz")
        with self.assertRaisesRegex(ValueError, "regular files"):
            firmware.verify_firmware(self.directory)

    def test_wrong_count(self):
        with self.assertRaisesRegex(ValueError, "Expected 17"):
            firmware.verify_firmware(self.directory, 17)

    def test_no_images(self):
        for name in self.entries:
            (self.directory / name).unlink()
        with self.assertRaisesRegex(ValueError, "No firmware"):
            firmware.verify_firmware(self.directory)

    def test_requested_device_dropped(self):
        self.metadata["profiles"].pop("board-b")
        self.write_metadata()
        with self.assertRaisesRegex(ValueError, "requested device: board-b"):
            firmware.verify_firmware(self.directory, config=self.config)

    def test_expected_image_missing_even_with_self_consistent_checksums(self):
        (self.directory / "b.img.gz").unlink()
        self.entries.pop("b.img.gz")
        self.write_manifest()
        with self.assertRaisesRegex(ValueError, "Device image mismatch"):
            firmware.verify_firmware(self.directory, config=self.config)

    def test_metadata_hash_mismatch(self):
        self.metadata["profiles"]["board-a"]["images"][0]["sha256"] = "0" * 64
        self.write_metadata()
        with self.assertRaisesRegex(ValueError, "metadata mismatch"):
            firmware.verify_firmware(self.directory, config=self.config)

    def test_docker_names_match_upstream_metadata(self):
        for name in self.entries:
            (self.directory / name).rename(self.directory / ("docker-" + name))
        self.entries = {"docker-" + name: digest for name, digest in self.entries.items()}
        self.write_manifest()
        self.assertEqual(firmware.verify_firmware(self.directory, 2, self.config, "docker"), 2)


class FakeGitHub:
    def __init__(self):
        self.release = None
        self.assets = []
        self.refs = []
        self.tag_object = None
        self.calls = []
        self.fail_upload = False
        self.corrupt_upload = False

    def draft(self):
        self.release = {"id": 123, "tag_name": "test-r1", "draft": True,
                        "target_commitish": SOURCE_SHA,
                        "html_url": "https://github.com/test/firmware/releases/tag/test-r1"}

    def __call__(self, *args):
        self.calls.append(args)
        if args[0] == "api":
            endpoint = args[1]
            if "matching-refs" in endpoint:
                return json.dumps(self.refs)
            if "/git/tags/" in endpoint:
                return json.dumps({"object": self.tag_object})
            if "/assets?" in endpoint:
                return json.dumps([self.assets])
            if endpoint.endswith("/releases?per_page=100"):
                return json.dumps([[self.release] if self.release else []])
        elif args[:2] == ("release", "create"):
            assert "--draft" in args
            assert args[args.index("--target") + 1] == SOURCE_SHA
            self.draft()
            return self.release["html_url"]
        elif args[:2] == ("release", "upload"):
            assert self.release["draft"]
            assert "--clobber" not in args
            if self.fail_upload:
                raise subprocess.CalledProcessError(1, args, stderr="fixture upload failure")
            path = Path(args[3])
            self.assets.append({"name": path.name, "size": path.stat().st_size,
                                "state": "uploaded", "digest": "sha256:" + (
                                    "0" * 64 if self.corrupt_upload else firmware.sha256(path))})
            return ""
        elif args[:2] == ("release", "edit"):
            assert "--draft=false" in args
            self.release["draft"] = False
            return ""
        raise AssertionError(f"Unexpected gh call: {args}")


class PublishingTests(FirmwareFixture):
    def setUp(self):
        super().setUp()
        self.github = FakeGitHub()
        self.patcher = patch.object(publisher, "gh", self.github)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def publish(self):
        return publisher.publish(self.directory, "test/firmware", "test-r1", "Test firmware",
                                 SOURCE_SHA, self.notes, expected_count=2)

    def test_publish_only_after_all_assets_verified(self):
        count, url = self.publish()
        self.assertEqual(count, 2)
        self.assertEqual(len(self.github.assets), len(list(self.directory.iterdir())))
        self.assertFalse(self.github.release["draft"])
        self.assertEqual(self.github.calls[-1][:2], ("release", "edit"))

    def test_upload_failure_leaves_draft(self):
        self.github.fail_upload = True
        with self.assertRaises(subprocess.CalledProcessError):
            self.publish()
        self.assertTrue(self.github.release["draft"])
        self.assertFalse(any(call[:2] == ("release", "edit") for call in self.github.calls))

    def test_remote_digest_mismatch_prevents_publication(self):
        self.github.corrupt_upload = True
        with self.assertRaisesRegex(ValueError, "size/SHA256"):
            self.publish()
        self.assertTrue(self.github.release["draft"])

    def test_public_release_never_modified(self):
        self.github.draft()
        self.github.release["draft"] = False
        with self.assertRaisesRegex(ValueError, "already public"):
            self.publish()
        self.assertTrue(all(call[0] == "api" for call in self.github.calls))

    def test_wrong_draft_target_rejected(self):
        self.github.draft()
        self.github.release["target_commitish"] = "main"
        with self.assertRaisesRegex(ValueError, "target does not match"):
            self.publish()
        self.assertTrue(all(call[0] == "api" for call in self.github.calls))

    def test_existing_tag_wrong_commit_rejected_before_writes(self):
        self.github.refs = [{"ref": "refs/tags/test-r1", "object": {"type": "commit", "sha": "b" * 40}}]
        with self.assertRaisesRegex(ValueError, "does not point"):
            self.publish()
        self.assertTrue(all(call[0] == "api" for call in self.github.calls))

    def test_annotated_tag_points_to_correct_commit(self):
        self.github.refs = [{"ref": "refs/tags/test-r1", "object": {"type": "tag", "sha": "b" * 40}}]
        self.github.tag_object = {"type": "commit", "sha": SOURCE_SHA}
        self.publish()

    def test_resume_identical_draft_skips_uploaded_files(self):
        self.github.draft()
        path = self.directory / "a.img.gz"
        self.github.assets = [{"name": path.name, "size": path.stat().st_size,
                               "state": "uploaded", "digest": "sha256:" + firmware.sha256(path)}]
        self.publish()
        uploaded = [Path(call[3]).name for call in self.github.calls if call[:2] == ("release", "upload")]
        self.assertNotIn("a.img.gz", uploaded)

    def test_unexpected_draft_asset_rejected(self):
        self.github.draft()
        self.github.assets = [{"name": "old.img.gz"}]
        with self.assertRaisesRegex(ValueError, "Unexpected"):
            self.publish()
        self.assertTrue(all(call[0] == "api" for call in self.github.calls))

    def test_invalid_manifest_rejected_before_any_github_call(self):
        self.manifest.write_text(f"{self.entries['a.img.gz']}  a.img.gz\n" * 2)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.publish()
        self.assertEqual(self.github.calls, [])


class ConfigurationTests(unittest.TestCase):
    def test_docker_overlay_uses_current_dockerman_dependencies(self):
        overlay = (REPO / "immortalwrt/rockchip/docker.config").read_text().splitlines()
        self.assertIn("CONFIG_PACKAGE_luci-app-dockerman=y", overlay)
        self.assertIn("CONFIG_PACKAGE_ucode-mod-socket=y", overlay)
        self.assertNotIn("CONFIG_PACKAGE_luci-lib-docker=y", overlay)

    def test_full_composed_config_is_checked(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temporary:
            root = Path(temporary)
            requested = root / "requested"
            resolved = root / "resolved"
            requested.write_text("CONFIG_PACKAGE_docker=y\n")
            resolved.write_text("# CONFIG_PACKAGE_docker is not set\n")
            command = ["bash", str(SCRIPTS / "check-resolved-config.sh"), str(resolved), str(requested)]
            env = {**os.environ, "TMPDIR": str(root)}
            result = subprocess.run(command, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("CONFIG_PACKAGE_docker: requested=y, resolved=n", result.stderr)
            resolved.write_text(requested.read_text())
            self.assertEqual(subprocess.run(command, env=env, capture_output=True).returncode, 0)

    def test_workflows_use_guards_and_actual_source_commit(self):
        build = yaml.safe_load((REPO / ".github/workflows/build-rockchip.yml").read_text())
        steps = {s["name"]: s for s in build["jobs"]["build"]["steps"]}
        config = steps["Load firmware configuration"]["run"]
        self.assertLess(config.index("cp .config .config.requested"), config.index("make defconfig"))
        self.assertLess(config.index("make defconfig"), config.index("check-resolved-config.sh"))
        self.assertIn(".config .config.requested", config)
        self.assertIn("docker.config", config)
        self.assertIn("scripts/firmware.py", steps["Prepare firmware files"]["run"])
        self.assertIn("--config openwrt/.config.requested", steps["Prepare firmware files"]["run"])
        release = steps["Publish GitHub Release"]
        self.assertEqual(release["env"]["SOURCE_SHA"], "${{ github.sha }}")
        self.assertIn("scripts/publish-firmware.py", release["run"])
        self.assertIn('--source-sha "$SOURCE_SHA"', release["run"])
        ci = yaml.safe_load((REPO / ".github/workflows/validate.yml").read_text())
        self.assertEqual(set(ci["jobs"]["upstream-config"]["strategy"]["matrix"]["profile"]),
                         {"standard", "docker"})
        promotion = yaml.safe_load((REPO / ".github/workflows/publish-rockchip-release.yml").read_text())
        promotion_steps = {s["name"]: s for s in promotion["jobs"]["publish"]["steps"]}
        self.assertIn("scripts/firmware.py", promotion_steps["Verify firmware checksums"]["run"])
        self.assertIn("scripts/publish-firmware.py", promotion_steps["Publish GitHub Release assets"]["run"])

    def test_documented_checksum_name(self):
        for path in (REPO / "README.md", REPO / "docs/FLASHING.md", REPO / "docs/MAINTENANCE.md"):
            text = path.read_text()
            self.assertIn("FIRMWARE_SHA256SUMS", text)
            self.assertNotRegex(text, r"(?<![A-Z_])SHA256SUMS")


if __name__ == "__main__":
    unittest.main()
