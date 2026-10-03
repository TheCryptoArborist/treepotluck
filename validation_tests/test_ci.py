"""CI collector unit tests use synthetic evidence; they do NOT execute Sui."""
from __future__ import annotations

import copy
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import ci_validate as ci
import verify_move as vm


def digest(data: bytes) -> str:
    return sha256(data).hexdigest()


class EvidenceCollectorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "move/sources").mkdir(parents=True)
        (self.root / "move/tests").mkdir()
        (self.root / "move/sources/config.move").write_text(
            "const LIVE_CREATION_ENABLED: bool = false;\n")
        (self.root / "move/tests/synthetic.move").write_text("#[test]\nfun synthetic() {}\n")
        shutil.copy2(ROOT / "toolchain-lock.json", self.root / "toolchain-lock.json")
        self.run = self.root / "evidence/validation-runs/synthetic-collector-fixture"
        self.run.mkdir(parents=True)
        self.result = self.run / "result.json"
        self.report = {
            "status": "PASSED_LOCAL_VALIDATION_ONLY", "ready_for_live_funds": False,
            "source_unchanged": True, "move_build": "PASSED", "move_tests": "PASSED",
            "boundary_probes": "PASSED", "toolchain_acquisition": "VERIFIED_ARCHIVE_INSTALLED",
            "pinned_toolchain": {key: json.loads((ROOT / "toolchain-lock.json").read_text())[key]
                                 for key in ("tag", "version", "commit")},
            "steps": [], "authored_move_tests": 1,
            "move_test_summary": {"total": 1, "passed": 1, "failed": 0},
            "production_bytecode_sha256": {},
        }
        text_by_stage = {
            "sui-version": "sui 1.80.1-synthetic-fixture\n",
            "move-tests": "Test result: OK. Total tests: 1; passed: 1; failed: 0\n",
            "probe-receipt_transfer": "error[E05001]: sources/probe.move: store ability constraint\n",
            "probe-escrow_access": "error[E05001]: sources/probe.move: escrow private\n",
            "probe-private_draw": "error[E05001]: sources/probe.move: draw private\n",
            "probe-test_helper": "error[E05001]: sources/probe.move: create_for_testing unbound\n",
        }
        for i, name in enumerate(ci.EXPECTED_STEPS):
            data = text_by_stage.get(name, "SYNTHETIC COLLECTOR FIXTURE ONLY\n").encode()
            filename = f"{i + 1:02d}-{name}.log"
            (self.run / filename).write_bytes(data)
            normal = name in ci.NORMAL_STEPS
            self.report["steps"].append({"name": name, "log": filename, "log_sha256": digest(data),
                "exit_code": 0 if normal else 1,
                "status": "SUCCEEDED" if normal else "EXPECTED_BOUNDARY_REJECTION"})
        (self.run / "production-bytecode").mkdir()
        for name in vm.MODULES:
            data = ("NOT REAL BYTECODE: " + name).encode()
            (self.run / f"production-bytecode/{name}.mv").write_bytes(data)
            self.report["production_bytecode_sha256"][name] = digest(data)
        (self.run / "Move.lock").write_bytes(b"synthetic dependency lock\n")
        self.report["move_lock_sha256"] = digest(b"synthetic dependency lock\n")
        self.report["source_files"] = vm.source_fingerprint(self.root)
        self.save()

    def save(self):
        self.result.write_text(json.dumps(self.report), encoding="utf-8")

    def assert_rejected(self, exit_code=0):
        self.save()
        with self.assertRaises((ci.EvidenceError, vm.ValidationError)):
            ci.verify_success(self.root, self.result, exit_code)

    def test_complete_synthetic_evidence_is_accepted_by_collector(self):
        self.assertEqual(ci.verify_success(self.root, self.result, 0)["move_tests"], "PASSED")

    def test_nonzero_exit_cannot_be_a_pass(self):
        self.assert_rejected(2)

    def test_blocked_status_cannot_be_a_pass(self):
        self.report["status"] = "BLOCKED"
        self.assert_rejected()

    def test_claim_of_live_readiness_is_rejected(self):
        self.report["ready_for_live_funds"] = True
        self.assert_rejected()

    def test_incomplete_compiler_stages_are_rejected(self):
        self.report["move_build"] = "NOT_RUN"
        self.assert_rejected()

    def test_edited_source_cannot_reuse_old_pass(self):
        (self.root / "move/tests/synthetic.move").write_text("// changed\n")
        self.assert_rejected()

    def test_declared_source_changes_are_rejected(self):
        self.report["source_unchanged"] = False
        self.assert_rejected()

    def test_unverified_compiler_is_rejected(self):
        self.report["toolchain_acquisition"] = "EXISTING_BINARY_VERSION_CHECK_ONLY"
        self.assert_rejected()

    def test_wrong_toolchain_lock_is_rejected(self):
        self.report["pinned_toolchain"]["version"] = "1.81.0"
        self.assert_rejected()

    def test_missing_stage_is_rejected(self):
        self.report["steps"].pop()
        self.assert_rejected()

    def test_tampered_log_is_rejected(self):
        (self.run / self.report["steps"][0]["log"]).write_text("changed")
        self.assert_rejected()

    def test_missing_log_is_rejected(self):
        (self.run / self.report["steps"][0]["log"]).unlink()
        self.assert_rejected()

    def test_missing_bytecode_is_rejected(self):
        (self.run / "production-bytecode/rounds.mv").unlink()
        self.assert_rejected()

    def test_tampered_bytecode_is_rejected(self):
        (self.run / "production-bytecode/rounds.mv").write_text("changed")
        self.assert_rejected()

    def test_tampered_dependency_lock_is_rejected(self):
        (self.run / "Move.lock").write_text("changed")
        self.assert_rejected()

    def test_incorrect_test_count_is_rejected(self):
        self.report["move_test_summary"]["total"] = 0
        self.assert_rejected()

    def test_successfully_compiled_attack_is_rejected(self):
        self.report["steps"][-1]["exit_code"] = 0
        self.assert_rejected()

    def test_dependency_error_cannot_count_as_expected_attack_rejection(self):
        step = self.report["steps"][-1]
        data = b"Could not download framework dependency\n"
        (self.run / step["log"]).write_bytes(data)
        step["log_sha256"] = digest(data)
        self.assert_rejected()

    def test_external_paths_are_rejected(self):
        for name in ("../outside", "/etc/passwd", "C:\\Users\\secret", "file:bad"):
            with self.subTest(name=name), self.assertRaises(ci.EvidenceError):
                ci.checked_path(self.run, name)

    def test_export_only_copies_explicit_returned_run(self):
        older = self.run.parent / "older-run"
        older.mkdir()
        (older / "old.log").write_text("old evidence")
        output = self.root / "export"
        output.mkdir()
        ci.export_run(self.root, self.result, output)
        self.assertTrue((output / "validation/result.json").is_file())
        self.assertFalse(any(path.name == "old.log" for path in output.rglob("*")))

    def test_external_report_cannot_be_exported(self):
        with self.assertRaises(ci.EvidenceError):
            ci.export_run(self.root, self.root / "outside/result.json", self.root / "export")

    def test_no_secret_environment_dump(self):
        with patch.dict(os.environ, {"A_SECRET_FOR_TEST": "do-not-include", "GITHUB_ACTIONS": "false"}), \
             patch.object(ci.subprocess, "run", side_effect=FileNotFoundError()):
            context = ci.build_context(self.root)
        self.assertNotIn("A_SECRET_FOR_TEST", context)

    def test_github_run_requires_verifiable_checked_out_commit(self):
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true", "GITHUB_SHA": "a" * 40}), \
             patch.object(ci.subprocess, "run", side_effect=FileNotFoundError()), \
             self.assertRaises(ci.EvidenceError):
            ci.build_context(self.root)


class WorkflowSourceChecks(unittest.TestCase):
    def test_validation_only_workflow_has_events_and_read_only_permissions(self):
        text = (ROOT / ".github/workflows/move-validation.yml").read_text()
        for required in ("  push:", "  pull_request:", "  workflow_dispatch:",
                         "  contents: read", "persist-credentials: false", "if: always()",
                         "run: python3 scripts/ci_validate.py", "path: ci-artifacts/"):
            self.assertIn(required, text)
        for prohibited in ("pull_request_target:", "secrets.", "sui client publish", "write-all"):
            self.assertNotIn(prohibited, text)

    def test_all_workflow_actions_are_pinned_to_full_commit_hashes(self):
        import re
        text = (ROOT / ".github/workflows/move-validation.yml").read_text()
        uses = re.findall(r"uses:\s+(\S+)", text)
        self.assertEqual(len(uses), 2)
        for action in uses:
            self.assertRegex(action, r"^[\w.-]+/[\w.-]+@[0-9a-f]{40}$")


if __name__ == "__main__":
    unittest.main()
