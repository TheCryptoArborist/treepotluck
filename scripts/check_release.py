"""Read-only handoff completeness check, NOT an audit or onchain security control."""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
settings = json.loads((root / "sample-settings.json").read_text())
required = [
    "tree_treasury_address", "development_address", "approved_dex_pool_id",
    "approved_dex_package_id", "price_policy", "burn_authority_verification",
    "reserve_spending_policy", "tree_coin_type_live_verified",
    "move_compiler_verified", "move_tests_executed", "independent_security_review_completed",
]
missing = [name for name in required if not settings.get(name)]
if settings.get("example_only"):
    missing.append("user-approved launch settings (currently example_only)")
source = (root / "move/sources/config.move").read_text()
if "const LIVE_CREATION_ENABLED: bool = false;" in source:
    missing.append("compile-time creation interlock intentionally remains disabled")
if missing:
    print("NOT READY FOR LIVE FUNDS")
    for item in missing:
        print(" - " + item)
    raise SystemExit(2)
print("Metadata fields are populated, which is NOT proof of safety or approval.")
