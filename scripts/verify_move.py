#!/usr/bin/env python3
"""Version-pinned LOCAL validation. Never publishes or signs a transaction.

A successful run is compiler/unit-test evidence only, not an audit or approval
for live funds. An installer or compiler error writes BLOCKED/FAILED, never PASS.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import uuid

from toolchain import ToolchainError, install, load_lock, sha256_file

ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
MODULES = {"buyback", "config", "economics", "reserve", "rounds"}
PROBES = {
    "receipt_transfer": {"token": "store", "kinds": ("ability", "abilities", "constraint")},
    "escrow_access": {"token": "escrow", "kinds": ("private", "internal", "restricted", "invalid field")},
    "private_draw": {"token": "draw", "kinds": ("private", "internal", "visibility")},
    "test_helper": {"token": "create_for_testing", "kinds": ("unbound", "unresolved", "not found")},
}


class ValidationError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def source_fingerprint(root: Path) -> dict[str, str]:
    """Hash the exact editable inputs, excluding outputs/caches and old evidence."""
    selected = [root / "toolchain-lock.json", root / "sample-settings.json", root / "move/Move.toml", root / "move/Move.lock"]
    for folder in ("move/sources", "move/tests", "model", "scripts", "validation_tests", "probes", ".github"):
        selected += [p for p in (root / folder).rglob("*")
                     if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"]
    return {str(p.relative_to(root)).replace("\\", "/"): sha256_file(p)
            for p in sorted(set(selected)) if p.is_file()}


def authored_test_count(root: Path) -> int:
    return sum(len(re.findall(r"#\[\s*test(?=\s*[,\]])", p.read_text(encoding="utf-8")))
               for p in (root / "move").rglob("*.move") if "build" not in p.parts)


def check_version(output: str, expected: str) -> None:
    match = re.search(r"\bsui\s+(\d+\.\d+\.\d+)(?:[-+\s]|$)", output)
    if match is None or match.group(1) != expected:
        raise ValidationError(f"Expected Sui {expected}; received {output.strip()!r}.")


def check_move_summary(output: str, expected: int) -> dict:
    clean = ANSI.sub("", output)
    match = re.search(r"Test result:\s*OK\.\s*Total tests:\s*(\d+)\s*;\s*passed:\s*(\d+)\s*;\s*failed:\s*(\d+)", clean)
    if match is None:
        raise ValidationError("Missing a recognized successful Move test summary.")
    total, passed, failed = map(int, match.groups())
    if expected < 1 or total != expected or passed != expected or failed != 0:
        raise ValidationError(f"Expected all {expected} authored Move tests, got {match.group(0)}.")
    return {"total": total, "passed": passed, "failed": failed}


def check_probe_failure(output: str, returncode: int, name: str) -> None:
    clean = ANSI.sub("", output).lower()
    rule = PROBES[name]
    if returncode == 0:
        raise ValidationError(f"Boundary probe {name} unexpectedly compiled.")
    if ("error[" not in clean or "probe.move" not in clean
            or rule["token"] not in clean or not any(kind in clean for kind in rule["kinds"])):
        raise ValidationError(f"{name} failed without the expected boundary diagnostic. Review log; not counted as a pass.")


def assert_interlock(root: Path) -> None:
    source = (root / "move/sources/config.move").read_text(encoding="utf-8")
    source = re.sub(r"/\*.*?\*/|//[^\n]*", "", source, flags=re.S)
    values = re.findall(r"const\s+LIVE_CREATION_ENABLED\s*:\s*bool\s*=\s*(true|false)\s*;", source)
    if values != ["false"]:
        raise ValidationError("This development validation bundle requires the live-creation interlock to remain false.")


def run_step(report: dict, evidence: Path, name: str, command: list[str], cwd: Path,
             timeout: int = 900, allow_failure: bool = False) -> tuple[int, str]:
    item = {"name": name, "command": command, "cwd": str(cwd), "started_utc": utc_now(), "status": "RUNNING"}
    report["steps"].append(item)
    env = dict(os.environ, NO_COLOR="1", TERM="dumb")
    try:
        result = subprocess.run(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                                errors="replace", timeout=timeout, check=False)
        code, output = result.returncode, result.stdout
    except subprocess.TimeoutExpired as exc:
        partial = exc.stdout or b""
        output = (partial.decode("utf-8", errors="replace") if isinstance(partial, bytes) else partial) + "\nVALIDATION TIMEOUT\n"
        code = 124
    except OSError as exc:
        code, output = 127, f"Executable could not run: {exc}\n"
    log = evidence / f"{len(report['steps']):02d}-{name}.log"
    log.write_text(output, encoding="utf-8")
    item.update({"finished_utc": utc_now(), "exit_code": code, "log": log.name,
                 "log_sha256": sha256_file(log),
                 "status": "SUCCEEDED" if code == 0 else "NONZERO_EXIT"})
    print(f"[{name}] exit {code}; log: {log.name}", flush=True)
    if code != 0 and not allow_failure:
        raise ValidationError(f"{name} failed (exit {code}); see {log.name}.")
    return code, output


def copy_move_package(root: Path, target: Path) -> None:
    # Never consume bytecode left by a previous/test-mode build.
    shutil.copytree(root / "move", target, ignore=shutil.ignore_patterns("build", "Published.toml", ".coverage*", ".trace*"))


def run_validation(root: Path, args: argparse.Namespace) -> tuple[int, Path]:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    evidence = root / "evidence" / "validation-runs" / run_id
    evidence.mkdir(parents=True)
    report = {"run_id": run_id, "started_utc": utc_now(), "status": "RUNNING",
              "ready_for_live_funds": False, "move_build": "NOT_RUN", "move_tests": "NOT_RUN",
              "boundary_probes": "NOT_RUN", "steps": [], "source_files": source_fingerprint(root),
              "authored_move_tests": authored_test_count(root),
              "limitations": ["Local evidence assumes a trustworthy host/compiler.",
                              "No network transactions, deployed-bytecode checks, or independent security audit.",
                              "Move unit tests do not prove production PTB gas/resource fairness."]}
    code = 2
    try:
        assert_interlock(root)
        lock = load_lock(root / "toolchain-lock.json")
        report["pinned_toolchain"] = {k: lock[k] for k in ("tag", "version", "commit")}
        run_step(report, evidence, "reference-model", [sys.executable, "-m", "unittest", "discover", "-s", "model", "-v"], root)
        run_step(report, evidence, "validation-harness", [sys.executable, "-m", "unittest", "discover", "-s", "validation_tests", "-v"], root)
        if args.install_toolchain or args.archive:
            report["toolchain_acquisition"] = "STARTED"
            sui = install(root, args.archive)
            report["toolchain_acquisition"] = "VERIFIED_ARCHIVE_INSTALLED"
        else:
            report["toolchain_acquisition"] = "EXISTING_BINARY_VERSION_CHECK_ONLY"
            selected = args.sui or shutil.which("sui")
            if not selected:
                raise ToolchainError("Sui CLI is unavailable. No Move build/test was run. Use --install-toolchain on a network-enabled machine.")
            sui = Path(selected).expanduser().resolve()
        _, version_output = run_step(report, evidence, "sui-version", [str(sui), "--version"], root, 30)
        check_version(version_output, lock["version"])
        report["compiler_binary_sha256"] = sha256_file(sui)
        report["compiler_version_output"] = version_output.strip()
        with tempfile.TemporaryDirectory(prefix="tree-pot-verify-") as directory:
            work = Path(directory)
            package = work / "under-test"
            copy_move_package(root, package)
            report["move_build"] = "STARTED"
            run_step(report, evidence, "move-build", [str(sui), "move", "build", "--build-env", "mainnet"], package)
            bytecode = {}
            output_dir = evidence / "production-bytecode"
            output_dir.mkdir()
            for path in (package / "build").rglob("*.mv"):
                if path.stem in MODULES and "dependencies" not in path.parts:
                    if path.stem in bytecode:
                        raise ValidationError("Ambiguous duplicate production module output.")
                    shutil.copy2(path, output_dir / path.name)
                    bytecode[path.stem] = sha256_file(path)
            if set(bytecode) != MODULES:
                raise ValidationError("Expected all five production bytecode modules; output is incomplete or unrecognized.")
            report["production_bytecode_sha256"] = bytecode
            generated_lock = package / "Move.lock"
            if not generated_lock.is_file():
                raise ValidationError("Compiler did not produce a dependency Move.lock.")
            shutil.copy2(generated_lock, evidence / "Move.lock")
            report["move_lock_sha256"] = sha256_file(generated_lock)
            report["move_build"] = "PASSED"
            report["move_tests"] = "STARTED"
            _, tests = run_step(report, evidence, "move-tests", [str(sui), "move", "test", "--build-env", "mainnet", "--coverage"], package)
            report["move_test_summary"] = check_move_summary(tests, report["authored_move_tests"])
            report["move_tests"] = "PASSED"
            # Fresh production copy for probes: never link against test-mode bytecode.
            clean = work / "production-dependency"
            copy_move_package(root, clean)
            shutil.copy2(generated_lock, clean / "Move.lock")
            report["boundary_probes"] = "STARTED"
            for name in ("positive_control", *PROBES):
                probe = work / name
                (probe / "sources").mkdir(parents=True)
                (probe / "Move.toml").write_text('[package]\nname = "boundary_probe"\nedition = "2024"\n\n[dependencies]\ntree_pot = { local = "../production-dependency" }\n', encoding="utf-8")
                shutil.copy2(root / "probes" / f"{name}.move", probe / "sources/probe.move")
                rc, text = run_step(report, evidence, "probe-" + name,
                                    [str(sui), "move", "build", "--build-env", "mainnet"], probe,
                                    allow_failure=name != "positive_control")
                if name != "positive_control":
                    check_probe_failure(text, rc, name)
                    report["steps"][-1]["status"] = "EXPECTED_BOUNDARY_REJECTION"
            report["boundary_probes"] = "PASSED"
        if source_fingerprint(root) != report["source_files"]:
            raise ValidationError("Source files changed during validation; results cannot certify these inputs.")
        report["status"] = "PASSED_LOCAL_VALIDATION_ONLY"
        code = 0
    except ToolchainError as exc:
        report["status"] = "BLOCKED"
        report["error"] = str(exc)
    except (ValidationError, OSError, ValueError, KeyError) as exc:
        report["status"] = "FAILED"
        report["error"] = str(exc)
        code = 1
    finally:
        for key in ("move_build", "move_tests", "boundary_probes"):
            if report[key] == "STARTED":
                report[key] = "FAILED"
        report["finished_utc"] = utc_now()
        report["source_unchanged"] = source_fingerprint(root) == report["source_files"]
        result_path = evidence / "result.json"
        result_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"{report['status']}: {report.get('error', 'Local validation only; live funds remain disabled.')}")
        print(f"Evidence: {result_path}")
    return code, result_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--install-toolchain", action="store_true", help="Download and verify the pinned official CLI into this package's .tools directory.")
    group.add_argument("--sui", type=Path, help="Use this installed CLI; exact version is checked.")
    group.add_argument("--archive", type=Path, help="Install from an already downloaded, checksum-matching official archive.")
    args = parser.parse_args()
    code, _ = run_validation(Path(__file__).resolve().parents[1], args)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
