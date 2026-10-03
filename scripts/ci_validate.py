#!/usr/bin/env python3
"""Run the existing validator and export ONLY its new evidence for GitHub Actions.

No keys, wallet calls, deployments, onchain transfers or repository mutations.
The report is consistency evidence, not independent proof of a trustworthy host.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess

import verify_move as vm
from toolchain import sha256_file

NORMAL_STEPS = (
    "reference-model", "validation-harness", "sui-version", "move-build",
    "move-tests", "probe-positive_control",
)
EXPECTED_STEPS = NORMAL_STEPS + tuple(f"probe-{name}" for name in vm.PROBES)


class EvidenceError(RuntimeError):
    pass


def checked_path(directory: Path, name: str) -> Path:
    """Accept a relative path contained in the specified evidence/source root."""
    if not isinstance(name, str) or not name or "\\" in name or ":" in name:
        raise EvidenceError("Invalid evidence path")
    rel = PurePosixPath(name)
    if rel.is_absolute() or ".." in rel.parts:
        raise EvidenceError("Evidence path escapes its root")
    path = directory.joinpath(*rel.parts)
    if not path.resolve().is_relative_to(directory.resolve()) or path.is_symlink():
        raise EvidenceError("Evidence path is not a contained regular file")
    if not path.is_file():
        raise EvidenceError(f"Evidence file is missing: {name}")
    return path


def verify_success(root: Path, result: Path, exit_code: int) -> dict:
    """Recheck the completed run against actual source, log and bytecode bytes."""
    if exit_code != 0:
        raise EvidenceError("A nonzero validation exit cannot be a pass")
    report = json.loads(result.read_text(encoding="utf-8"))
    if report.get("status") != "PASSED_LOCAL_VALIDATION_ONLY":
        raise EvidenceError("Run did not report a complete local validation pass")
    if report.get("ready_for_live_funds") is not False:
        raise EvidenceError("Unexpected live-funds readiness claim")
    if report.get("source_unchanged") is not True:
        raise EvidenceError("Sources changed during the run")
    if any(report.get(k) != "PASSED" for k in ("move_build", "move_tests", "boundary_probes")):
        raise EvidenceError("Missing completed compiler stage")
    if report.get("source_files") != vm.source_fingerprint(root):
        raise EvidenceError("Evidence does not match the current source revision")
    if report.get("toolchain_acquisition") != "VERIFIED_ARCHIVE_INSTALLED":
        raise EvidenceError("Compiler archive was not verified by the installer")
    lock = vm.load_lock(root / "toolchain-lock.json")
    if report.get("pinned_toolchain") != {k: lock[k] for k in ("tag", "version", "commit")}:
        raise EvidenceError("Toolchain metadata differs from this revision's lock")
    steps = report.get("steps", [])
    if [step.get("name") for step in steps] != list(EXPECTED_STEPS):
        raise EvidenceError("Missing, reordered or duplicate validation steps")
    texts = {}
    for step in steps:
        name = step["name"]
        path = checked_path(result.parent, step["log"])
        if sha256_file(path) != step.get("log_sha256"):
            raise EvidenceError(f"Log digest mismatch: {name}")
        text = path.read_text(encoding="utf-8")
        texts[name] = text
        if name in NORMAL_STEPS:
            if step.get("exit_code") != 0 or step.get("status") != "SUCCEEDED":
                raise EvidenceError(f"Required stage did not succeed: {name}")
        else:
            if step.get("status") != "EXPECTED_BOUNDARY_REJECTION":
                raise EvidenceError(f"Probe was not an expected rejection: {name}")
            vm.check_probe_failure(text, step["exit_code"], name.removeprefix("probe-"))
    vm.check_version(texts["sui-version"], lock["version"])
    expected = vm.authored_test_count(root)
    summary = vm.check_move_summary(texts["move-tests"], expected)
    if report.get("authored_move_tests") != expected or report.get("move_test_summary") != summary:
        raise EvidenceError("Recorded Move test counts do not match the actual suite")
    modules = report.get("production_bytecode_sha256", {})
    if set(modules) != vm.MODULES:
        raise EvidenceError("Incomplete production bytecode evidence")
    for name, digest in modules.items():
        if sha256_file(checked_path(result.parent, f"production-bytecode/{name}.mv")) != digest:
            raise EvidenceError(f"Bytecode digest mismatch: {name}")
    if sha256_file(checked_path(result.parent, "Move.lock")) != report.get("move_lock_sha256"):
        raise EvidenceError("Dependency lock digest mismatch")
    vm.assert_interlock(root)
    return report


def build_context(root: Path) -> dict:
    """Record a small allowlist, never dump environment variables or secrets."""
    context = {key: os.environ[key] for key in (
        "GITHUB_REPOSITORY", "GITHUB_SHA", "GITHUB_REF", "GITHUB_RUN_ID",
        "GITHUB_RUN_ATTEMPT", "GITHUB_EVENT_NAME", "RUNNER_OS", "RUNNER_ARCH",
    ) if key in os.environ}
    try:
        git = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True,
                             text=True, timeout=10, check=False)
        if git.returncode == 0 and re.fullmatch(r"[0-9a-f]{40}", git.stdout.strip()):
            context["checked_out_commit"] = git.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    if os.environ.get("GITHUB_ACTIONS") == "true":
        actual = context.get("checked_out_commit")
        if not actual or actual != context.get("GITHUB_SHA"):
            raise EvidenceError("Checked-out revision differs from GitHub's run SHA")
    return context


def export_run(root: Path, result: Path, output: Path) -> None:
    """Copy this invocation's returned run path, not the 'latest' stored report."""
    evidence_root = (root / "evidence/validation-runs").resolve()
    source = result.parent.resolve()
    if not source.is_relative_to(evidence_root):
        raise EvidenceError("Returned report is outside the validation directory")
    shutil.copytree(source, output / "validation", symlinks=False)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    output = root / "ci-artifacts"
    # Refuse stale output rather than silently including evidence from an earlier run.
    output.mkdir(exist_ok=False)
    metadata = {"started_utc": datetime.now(timezone.utc).isoformat(),
                "status": "RUNNING", "ready_for_live_funds": False}
    result = None
    code = 1
    try:
        metadata["context"] = build_context(root)
        args = argparse.Namespace(install_toolchain=True, archive=None, sui=None)
        code, result = vm.run_validation(root, args)
        report = json.loads(result.read_text(encoding="utf-8"))
        metadata["validation_run_id"] = report.get("run_id")
        metadata["status"] = report.get("status", "FAILED")
        metadata["error"] = report.get("error")
        if code == 0:
            verify_success(root, result, code)
            metadata["evidence_consistency"] = "PASSED"
        else:
            metadata["evidence_consistency"] = "NOT_A_SUCCESSFUL_RUN"
    except Exception as exc:
        metadata["status"] = "FAILED"
        metadata["error"] = str(exc)
        code = 1
    finally:
        try:
            if result is not None:
                export_run(root, result, output)
        except Exception as exc:
            metadata["status"] = "FAILED"
            metadata["evidence_export_error"] = str(exc)
            code = 1
        metadata["finished_utc"] = datetime.now(timezone.utc).isoformat()
        (output / "ci-context.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        text = ("# Pot Luck compiler validation\n\n"
                f"Status: **{metadata['status']}**\n\n"
                "Live entries remain disabled. This is build/test evidence, not a launch approval or audit.\n\n"
                "See ci-context.json and validation/result.json for the tested revision and recorded stages.\n")
        (output / "SUMMARY.md").write_text(text, encoding="utf-8")
        summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary_path:
            with open(summary_path, "a", encoding="utf-8") as stream:
                stream.write(text)
        print(text)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
