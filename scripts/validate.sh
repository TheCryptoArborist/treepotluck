#!/usr/bin/env bash
# Local validation only. Pass --install-toolchain for an opt-in pinned CLI download.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 "$ROOT/scripts/verify_move.py" "$@"
