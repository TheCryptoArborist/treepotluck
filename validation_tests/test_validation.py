"""Tests of validation tooling ONLY. Mock outputs are not Sui/Move execution."""
from __future__ import annotations

import copy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import toolchain
import verify_move as vm


class ArchiveSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def archive(self, members):
        path = self.root / "archive.tgz"
        with tarfile.open(path, "w:gz") as tar:
            for name, content, kind in members:
                item = tarfile.TarInfo(name)
                item.type = kind
                item.size = len(content) if kind == tarfile.REGTYPE else 0
                if kind in (tarfile.SYMTYPE, tarfile.LNKTYPE):
                    item.linkname = "/outside"
                tar.addfile(item, io.BytesIO(content) if item.size else None)
        return path

    def test_extracts_only_cli_not_other_files(self):
        archive = self.archive([("release/sui", b"fixture-cli", tarfile.REGTYPE),
                                ("release/other", b"do-not-extract", tarfile.REGTYPE)])
        destination = self.root / "bin/sui"
        toolchain.extract_cli(archive, destination, "sui")
        self.assertEqual(destination.read_bytes(), b"fixture-cli")
        self.assertEqual([p.name for p in destination.parent.iterdir()], ["sui"])

    def test_rejects_parent_traversal(self):
        archive = self.archive([("../sui", b"bad", tarfile.REGTYPE)])
        with self.assertRaises(toolchain.ToolchainError):
            toolchain.extract_cli(archive, self.root / "out/sui", "sui")

    def test_rejects_absolute_member(self):
        archive = self.archive([("/sui", b"bad", tarfile.REGTYPE)])
        with self.assertRaises(toolchain.ToolchainError):
            toolchain.extract_cli(archive, self.root / "out/sui", "sui")

    def test_rejects_backslash_path(self):
        archive = self.archive([("bad\\segment/sui", b"bad", tarfile.REGTYPE)])
        with self.assertRaises(toolchain.ToolchainError):
            toolchain.extract_cli(archive, self.root / "out/sui", "sui")

    def test_rejects_symlink_cli(self):
        archive = self.archive([("sui", b"", tarfile.SYMTYPE)])
        with self.assertRaises(toolchain.ToolchainError):
            toolchain.extract_cli(archive, self.root / "out/sui", "sui")

    def test_rejects_hardlink_cli(self):
        archive = self.archive([("sui", b"", tarfile.LNKTYPE)])
        with self.assertRaises(toolchain.ToolchainError):
            toolchain.extract_cli(archive, self.root / "out/sui", "sui")

    def test_rejects_missing_cli(self):
        archive = self.archive([("other", b"hi", tarfile.REGTYPE)])
        with self.assertRaises(toolchain.ToolchainError):
            toolchain.extract_cli(archive, self.root / "out/sui", "sui")

    def test_rejects_duplicate_cli_names(self):
        archive = self.archive([("one/sui", b"1", tarfile.REGTYPE), ("two/sui", b"2", tarfile.REGTYPE)])
        with self.assertRaises(toolchain.ToolchainError):
            toolchain.extract_cli(archive, self.root / "out/sui", "sui")

    def test_rejects_empty_cli(self):
        archive = self.archive([("sui", b"", tarfile.REGTYPE)])
        with self.assertRaises(toolchain.ToolchainError):
            toolchain.extract_cli(archive, self.root / "out/sui", "sui")

    def test_verified_archive_matches_digest(self):
        path = self.root / "small"
        path.write_bytes(b"valid")
        toolchain.verify_archive(path, {"size": 5, "sha256": hashlib.sha256(b"valid").hexdigest()})

    def test_corrupt_archive_digest_aborts(self):
        path = self.root / "small"
        path.write_bytes(b"wrong")
        with self.assertRaises(toolchain.ToolchainError):
            toolchain.verify_archive(path, {"size": 5, "sha256": hashlib.sha256(b"valid").hexdigest()})

    def test_wrong_archive_size_aborts(self):
        path = self.root / "small"
        path.write_bytes(b"bad")
        with self.assertRaises(toolchain.ToolchainError):
            toolchain.verify_archive(path, {"size": 4, "sha256": toolchain.sha256_file(path)})


class ToolchainManifestTests(unittest.TestCase):
    def setUp(self):
        self.lock = toolchain.load_lock(ROOT / "toolchain-lock.json")

    def test_mainnet_release_is_pinned(self):
        self.assertEqual(self.lock["tag"], "mainnet-v1.80.1")
        self.assertEqual(len(self.lock["assets"]), 5)

    def test_platform_aliases(self):
        self.assertEqual(toolchain.platform_key("Windows", "AMD64"), "Windows-x86_64")
        self.assertEqual(toolchain.platform_key("Darwin", "arm64"), "Darwin-aarch64")

    def test_release_urls_are_official_and_https(self):
        for asset in self.lock["assets"].values():
            self.assertTrue(toolchain.archive_url(self.lock, asset).startswith(
                "https://github.com/MystenLabs/sui/releases/download/mainnet-v1.80.1/"))

    def test_missing_checksum_is_rejected(self):
        lock = copy.deepcopy(self.lock)
        lock["assets"]["Windows-x86_64"]["sha256"] = ""
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "lock.json"
            path.write_text(json.dumps(lock))
            with self.assertRaises(toolchain.ToolchainError):
                toolchain.load_lock(path)

    def test_testnet_tag_is_rejected(self):
        lock = copy.deepcopy(self.lock)
        lock["tag"] = "testnet-v1.80.1"
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "lock.json"
            path.write_text(json.dumps(lock))
            with self.assertRaises(toolchain.ToolchainError):
                toolchain.load_lock(path)


class ResultGuardTests(unittest.TestCase):
    def test_exact_version_is_accepted(self):
        vm.check_version("sui 1.80.1-782577ca40c9", "1.80.1")

    def test_other_version_is_rejected(self):
        with self.assertRaises(vm.ValidationError):
            vm.check_version("sui 1.81.0-xyz", "1.80.1")

    def test_non_version_text_is_rejected(self):
        with self.assertRaises(vm.ValidationError):
            vm.check_version("download failed", "1.80.1")

    def test_complete_mock_move_summary_is_recognized(self):
        result = vm.check_move_summary("Test result: OK. Total tests: 51; passed: 51; failed: 0", 51)
        self.assertEqual(result, {"total": 51, "passed": 51, "failed": 0})

    def test_empty_success_output_is_not_a_test_pass(self):
        with self.assertRaises(vm.ValidationError):
            vm.check_move_summary("", 51)

    def test_zero_tests_is_not_a_pass(self):
        with self.assertRaises(vm.ValidationError):
            vm.check_move_summary("Test result: OK. Total tests: 0; passed: 0; failed: 0", 51)

    def test_filtered_suite_is_rejected(self):
        with self.assertRaises(vm.ValidationError):
            vm.check_move_summary("Test result: OK. Total tests: 1; passed: 1; failed: 0", 51)

    def test_reported_failure_is_rejected(self):
        with self.assertRaises(vm.ValidationError):
            vm.check_move_summary("Test result: OK. Total tests: 51; passed: 50; failed: 1", 51)

    def test_ansi_color_is_removed_for_parsing(self):
        result = vm.check_move_summary("\x1b[32mTest result: OK. Total tests: 51; passed: 51; failed: 0\x1b[0m", 51)
        self.assertEqual(result["passed"], 51)

    def test_dependency_failure_is_not_boundary_success(self):
        with self.assertRaises(vm.ValidationError):
            vm.check_probe_failure("Could not resolve github.com; dependency fetch failed", 1, "receipt_transfer")

    def test_unexpected_boundary_compilation_is_rejected(self):
        with self.assertRaises(vm.ValidationError):
            vm.check_probe_failure("BUILDING boundary_probe", 0, "receipt_transfer")

    def test_mock_expected_boundary_error_is_recognized(self):
        vm.check_probe_failure("error[E05001]: ability constraint sources/probe.move: missing store", 1, "receipt_transfer")

    def test_wrong_diagnostic_is_not_accepted(self):
        with self.assertRaises(vm.ValidationError):
            vm.check_probe_failure("error[E03001]: sources/probe.move: unknown syntax", 1, "receipt_transfer")

    def test_live_interlock_is_disabled(self):
        vm.assert_interlock(ROOT)

    def test_commented_out_interlock_cannot_satisfy_guard(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "move/sources").mkdir(parents=True)
            (root / "move/sources/config.move").write_text(
                "// const LIVE_CREATION_ENABLED: bool = false;\nconst LIVE_CREATION_ENABLED: bool = true;\n")
            with self.assertRaises(vm.ValidationError):
                vm.assert_interlock(root)

    def test_counts_all_56_authored_move_tests(self):
        self.assertEqual(vm.authored_test_count(ROOT), 56)

    def test_source_fingerprint_covers_build_inputs_not_old_logs(self):
        before = vm.source_fingerprint(ROOT)
        self.assertIn("move/sources/economics.move", before)
        self.assertIn("toolchain-lock.json", before)
        self.assertIn("probes/receipt_transfer.move", before)
        self.assertFalse(any("evidence/" in path for path in before))

    def test_failed_command_is_logged_and_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report = {"steps": []}
            with self.assertRaises(vm.ValidationError):
                vm.run_step(report, root, "fixture-failure", [sys.executable, "-c", "raise SystemExit(7)"], root)
            self.assertEqual(report["steps"][0]["exit_code"], 7)
            self.assertEqual(report["steps"][0]["status"], "NONZERO_EXIT")
            self.assertTrue((root / report["steps"][0]["log"]).is_file())

    def test_command_timeout_is_not_success(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report = {"steps": []}
            with patch.object(vm.subprocess, "run", side_effect=subprocess.TimeoutExpired(["fixture"], 1)):
                with self.assertRaises(vm.ValidationError):
                    vm.run_step(report, root, "fixture-timeout", ["fixture"], root, 1)
            self.assertEqual(report["steps"][0]["exit_code"], 124)

    def test_missing_executable_is_not_success(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            report = {"steps": []}
            with patch.object(vm.subprocess, "run", side_effect=FileNotFoundError("fixture unavailable")):
                with self.assertRaises(vm.ValidationError):
                    vm.run_step(report, root, "fixture-missing", ["fixture"], root)
            self.assertEqual(report["steps"][0]["exit_code"], 127)


if __name__ == "__main__":
    unittest.main()
