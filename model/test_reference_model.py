"""Run: python -m unittest discover -s model -v (from the repository root)."""
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import json
import random
import re
import unittest

from reference_model import (
    Allocation, Config, MAX_U64, MIST_PER_SUI, Phase, Receipt,
    RoundModel, RuleError, allocate, portion,
)


class AccountingTests(unittest.TestCase):
    def test_ten_one_sui_entries(self):
        self.assertEqual(allocate(10 * MIST_PER_SUI),
            Allocation(8_500_000_000, 1_000_000_000, 25_000_000, 275_000_000, 200_000_000))

    def test_one_hundred_sui_pot(self):
        a = allocate(100 * MIST_PER_SUI)
        self.assertEqual(a.winner, 85 * MIST_PER_SUI)
        self.assertEqual(a.treasury_buyback + a.burn_buyback, 10_250_000_000)

    def test_quarter_percent_burn_rounds_down_in_small_pots(self):
        self.assertEqual(allocate(399).burn_buyback, 0)
        self.assertEqual(allocate(400), Allocation(340, 40, 1, 11, 8))

    def test_one_thousand_sui_pot_uses_quarter_percent_burn(self):
        self.assertEqual(allocate(1000 * MIST_PER_SUI),
            Allocation(850_000_000_000, 100_000_000_000, 2_500_000_000,
                       27_500_000_000, 20_000_000_000))

    def test_zero_pot(self):
        self.assertEqual(allocate(0), Allocation(0, 0, 0, 0, 0))

    def test_rounding_dust_to_winner(self):
        self.assertEqual(allocate(1), Allocation(1, 0, 0, 0, 0))
        a = allocate(10_003)
        self.assertEqual(a.total, 10_003)
        self.assertEqual(a.winner, 8_503)

    def test_u64_maximum(self):
        self.assertEqual(allocate(MAX_U64).total, MAX_U64)
        self.assertEqual(portion(MAX_U64, 10_000), MAX_U64)

    def test_invalid_basis_points(self):
        for b in (-1, 10_001, 1.5, True):
            with self.assertRaises(RuleError):
                portion(100, b)

    def test_invalid_amounts(self):
        for v in (-1, MAX_U64 + 1, 1.1, True):
            with self.assertRaises(RuleError):
                allocate(v)

    def test_all_bps_at_boundary_values(self):
        for amount in (0, 1, 9_999, 10_000, 10_001, MAX_U64 - 1, MAX_U64):
            for bps in range(10_001):
                self.assertEqual(portion(amount, bps), amount * bps // 10_000)

    def test_one_hundred_thousand_random_gross_amounts(self):
        rng = random.Random(20261003)
        for _ in range(100_000):
            gross = rng.randrange(MAX_U64 + 1)
            a = allocate(gross)
            self.assertEqual(a.total, gross)
            self.assertEqual(a.treasury_buyback, gross * 1000 // 10_000)
            self.assertEqual(a.burn_buyback, gross * 25 // 10_000)
            self.assertEqual(a.reserve, gross * 275 // 10_000)
            self.assertEqual(a.development, gross * 200 // 10_000)
            self.assertGreaterEqual(a.winner * 10_000, gross * 8500)
            self.assertLess(a.winner * 10_000 - gross * 8500, 40_000)


class ConfigTests(unittest.TestCase):
    def test_invalid_thresholds(self):
        for threshold in (0, 1, 129, MAX_U64):
            with self.assertRaises(RuleError):
                Config(threshold=threshold)

    def test_entry_cannot_overflow_pot(self):
        with self.assertRaises(RuleError):
            Config(entry=MAX_U64, threshold=2)
        self.assertEqual(Config(entry=MAX_U64 // 2, threshold=2).entry, MAX_U64 // 2)

    def test_invalid_windows(self):
        for window in (0, 2_592_000_001):
            with self.assertRaises(RuleError):
                Config(window_ms=window)

    def test_zero_recipient_rejected(self):
        for values in ({"treasury": "0x0"}, {"development": "0x0"}):
            with self.assertRaises(RuleError):
                Config(**values)

    def test_configuration_is_immutable_in_model(self):
        c = Config()
        with self.assertRaises(FrozenInstanceError):
            c.threshold = 20

    def test_deadline_overflow_rejected(self):
        with self.assertRaises(RuleError):
            RoundModel(opened_at=MAX_U64)


class LifecycleTests(unittest.TestCase):
    def new_round(self, threshold=3, entry=1_000_000_000):
        return RoundModel(Config(threshold=threshold, entry=entry, window_ms=1000))

    def sealed(self, threshold=3):
        r = self.new_round(threshold)
        for i in range(threshold):
            r.join(f"player_{i}", r.config.entry, 0, f"join_{i}")
        return r

    def test_threshold_uses_active_entries(self):
        r = self.new_round()
        a = r.join("a", r.config.entry, 0, "j1")
        r.join("b", r.config.entry, 0, "j2")
        r.exit("a", a, 0)
        r.join("c", r.config.entry, 0, "j3")
        self.assertEqual(r.phase, Phase.OPEN)
        self.assertEqual(len(r.entries), 2)
        r.join("d", r.config.entry, 0, "j4")
        self.assertEqual(r.phase, Phase.SEALED)

    def test_no_fee_before_settlement(self):
        r = self.sealed()
        self.assertEqual(r.escrow, 3 * r.config.entry)
        self.assertIsNone(r.pending_buyback)
        self.assertIsNone(r.allocations)

    def test_wrong_payment_rolls_back(self):
        r = self.new_round()
        for amount in (0, r.config.entry - 1, r.config.entry + 1):
            before = deepcopy(r.__dict__)
            with self.assertRaisesRegex(RuleError, "wrong_payment"):
                r.join("a", amount, 0, "join")
            self.assertEqual(r.__dict__, before)

    def test_duplicate_wallet_rejected(self):
        r = self.new_round()
        r.join("a", r.config.entry, 0, "j1")
        with self.assertRaisesRegex(RuleError, "duplicate_wallet"):
            r.join("a", r.config.entry, 0, "j2")

    def test_full_round_rejects_new_entries(self):
        r = self.sealed()
        with self.assertRaisesRegex(RuleError, "not_open"):
            r.join("late", r.config.entry, 0, "late")

    def test_deadline_boundary(self):
        r = self.new_round()
        r.join("a", r.config.entry, r.deadline - 1, "before")
        with self.assertRaisesRegex(RuleError, "deadline_reached"):
            r.join("b", r.config.entry, r.deadline, "at")

    def test_early_exit_full_refund(self):
        r = self.new_round()
        receipt = r.join("a", r.config.entry, 0, "j")
        self.assertEqual(r.exit("a", receipt, 0), r.config.entry)
        self.assertEqual(r.escrow, 0)
        self.assertEqual(r.phase, Phase.OPEN)

    def test_exit_after_deadline_needs_no_prior_expire(self):
        r = self.new_round()
        receipt = r.join("a", r.config.entry, 0, "j")
        r.exit("a", receipt, r.deadline)
        self.assertEqual(r.phase, Phase.REFUNDING)
        self.assertEqual(r.escrow, 0)

    def test_expired_round_refunds_every_active_entry(self):
        r = self.new_round(4)
        receipts = [r.join(str(i), r.config.entry, 0, f"j{i}") for i in range(3)]
        r.expire(r.deadline)
        for receipt in reversed(receipts):
            self.assertEqual(r.exit(receipt.player, receipt, r.deadline + 100), r.config.entry)
        self.assertEqual(r.total_refunds, 3 * r.config.entry)
        self.assertEqual(r.escrow, 0)

    def test_expire_before_deadline_rejected(self):
        r = self.new_round()
        with self.assertRaisesRegex(RuleError, "not_expired"):
            r.expire(r.deadline - 1)

    def test_expired_round_cannot_reopen(self):
        r = self.new_round()
        r.expire(r.deadline)
        with self.assertRaisesRegex(RuleError, "not_open"):
            r.join("a", r.config.entry, 0, "j")

    def test_swap_remove_updates_index(self):
        r = self.new_round(5)
        a, b, c = [r.join(x, r.config.entry, 0, f"j{x}") for x in ("a", "b", "c")]
        r.exit("a", a, 0)
        self.assertEqual(r.by_receipt[c.id], 0)
        r.exit("c", c, 0)
        self.assertEqual(r.by_receipt[b.id], 0)
        r.exit("b", b, 0)
        self.assertEqual(r.entries, [])

    def test_exit_then_rejoin_uses_new_receipt(self):
        r = self.new_round()
        old = r.join("a", r.config.entry, 0, "j1")
        r.exit("a", old, 0)
        new = r.join("a", r.config.entry, 0, "j2")
        self.assertNotEqual(old.id, new.id)
        with self.assertRaises(RuleError):
            r.exit("a", old, 0)
        self.assertEqual(r.by_wallet["a"], new.id)

    def test_refund_cannot_be_replayed(self):
        r = self.new_round()
        receipt = r.join("a", r.config.entry, 0, "j")
        r.exit("a", receipt, 0)
        with self.assertRaises(RuleError):
            r.exit("a", receipt, 0)

    def test_wrong_sender_cannot_refund(self):
        r = self.new_round()
        receipt = r.join("a", r.config.entry, 0, "j")
        with self.assertRaisesRegex(RuleError, "not_owner"):
            r.exit("b", receipt, 0)

    def test_wrong_round_or_forged_receipt_rejected(self):
        r = self.new_round()
        a = r.join("a", r.config.entry, 0, "j")
        for fake in (replace(a, round_id="OTHER"), replace(a, amount=2), replace(a, id=999)):
            with self.assertRaises(RuleError):
                r.exit("a", fake, 0)
        self.assertEqual(r.escrow, r.config.entry)

    def test_sealed_round_no_exit_even_after_deadline(self):
        r = self.sealed()
        receipt = r.entries[0]
        with self.assertRaisesRegex(RuleError, "not_refundable"):
            r.exit(receipt.player, receipt, r.deadline + 1)

    def test_sealed_round_cannot_expire(self):
        r = self.sealed()
        with self.assertRaisesRegex(RuleError, "not_open"):
            r.expire(r.deadline + 1)

    def test_unfilled_round_cannot_draw(self):
        r = self.new_round()
        with self.assertRaisesRegex(RuleError, "not_sealed"):
            r.record_draw_fixture(0, "draw")

    def test_join_and_draw_same_transaction_rejected(self):
        r = self.sealed()
        with self.assertRaisesRegex(RuleError, "separate_transaction_required"):
            r.record_draw_fixture(0, r.seal_tx)

    def test_draw_and_settle_same_transaction_rejected(self):
        r = self.sealed()
        r.record_draw_fixture(0, "draw")
        with self.assertRaisesRegex(RuleError, "separate_transaction_required"):
            r.settle(r.config.reserve_id, "draw")

    def test_winner_cannot_be_redrawn(self):
        r = self.sealed()
        r.record_draw_fixture(1, "draw")
        with self.assertRaisesRegex(RuleError, "not_sealed"):
            r.record_draw_fixture(0, "retry")
        self.assertEqual(r.selected, 1)

    def test_invalid_draw_fixture_rejected(self):
        r = self.sealed()
        for index in (-1, 3):
            with self.assertRaisesRegex(RuleError, "invalid_index"):
                r.record_draw_fixture(index, "draw")

    def test_settlement_requires_committed_draw(self):
        r = self.sealed()
        with self.assertRaisesRegex(RuleError, "not_drawn"):
            r.settle(r.config.reserve_id, "settle")

    def test_wrong_reserve_rejected(self):
        r = self.sealed()
        r.record_draw_fixture(1, "draw")
        with self.assertRaisesRegex(RuleError, "wrong_reserve"):
            r.settle("ATTACKER_RESERVE", "settle")

    def test_failed_settlement_retries_same_winner(self):
        r = self.sealed()
        r.record_draw_fixture(1, "draw")
        before = deepcopy(r.__dict__)
        with self.assertRaisesRegex(RuleError, "simulated_settlement_abort"):
            r.settle(r.config.reserve_id, "attempt", simulate_abort=True)
        self.assertEqual(r.__dict__, before)
        r.settle(r.config.reserve_id, "retry")
        self.assertEqual(r.selected, 1)
        self.assertEqual(r.prize_recipient, "player_1")

    def test_settlement_cannot_be_replayed(self):
        r = self.sealed()
        r.record_draw_fixture(0, "draw")
        r.settle(r.config.reserve_id, "settle")
        with self.assertRaisesRegex(RuleError, "not_drawn"):
            r.settle(r.config.reserve_id, "again")

    def test_payout_and_earmarking_match_example(self):
        r = self.sealed(10)
        r.record_draw_fixture(4, "draw")
        a = r.settle(r.config.reserve_id, "settle")
        self.assertEqual(a.winner, 8_500_000_000)
        self.assertEqual(r.pending_buyback.treasury_budget, 0)
        self.assertEqual(r.treasury_paid_mist, MIST_PER_SUI)
        self.assertEqual(r.treasury_recipient, "TEST_TREASURY")
        self.assertEqual(r.pending_buyback.burn_budget, 25_000_000)
        self.assertEqual(r.prize_recipient, "player_4")
        self.assertEqual(r.development_recipient, "TEST_DEVELOPMENT")
        self.assertEqual(r.escrow, 0)

    def test_full_round_at_integer_limit(self):
        r = self.new_round(threshold=2, entry=MAX_U64 // 2)
        r.join("a", r.config.entry, 0, "a")
        r.join("b", r.config.entry, 0, "b")
        r.record_draw_fixture(0, "draw")
        a = r.settle(r.config.reserve_id, "settle")
        self.assertEqual(a.total, MAX_U64 - 1)

    def test_five_hundred_randomized_round_lifecycles(self):
        rng = random.Random(731)
        for trial in range(500):
            n = rng.randrange(2, 33)
            r = self.new_round(n, rng.randrange(1, MAX_U64 // n + 1))
            tx_count = 0
            # Valid random join/exit sequences, each independently invariant-checked.
            for _ in range(100):
                tx_count += 1
                if r.phase != Phase.OPEN:
                    break
                if r.entries and rng.random() < 0.45:
                    e = rng.choice(r.entries)
                    r.exit(e.player, e, 0)
                else:
                    r.join(f"{trial}_{tx_count}", r.config.entry, 0, str(tx_count))
            if r.phase == Phase.OPEN and rng.random() < 0.5:
                r.expire(r.deadline)
                while r.entries:
                    e = rng.choice(r.entries)
                    r.exit(e.player, e, r.deadline)
                self.assertEqual(r.escrow, 0)
            else:
                while r.phase == Phase.OPEN:
                    tx_count += 1
                    r.join(f"fill_{trial}_{tx_count}", r.config.entry, 0, str(tx_count))
                r.record_draw_fixture(rng.randrange(n), "draw")
                r.settle(r.config.reserve_id, "settle")
                self.assertEqual(r.allocations.total + r.total_refunds, r.total_deposits)
            r.invariants()


class SourceGuardChecks(unittest.TestCase):
    """Text regression checks only; these are NOT a Move parser or bytecode verifier."""
    root = Path(__file__).resolve().parents[1]

    def test_fee_constants_match_settings_and_reference_model(self):
        src = (self.root / "move/sources/economics.move").read_text()
        actual = {
            name: int(value.replace("_", ""))
            for name, value in re.findall(r"const (\w+_BPS): u64 = ([\d_]+);", src)
        }
        self.assertEqual(actual, {
            "TREASURY_BPS": 1000, "BURN_BPS": 25,
            "RESERVE_BPS": 275, "DEVELOPMENT_BPS": 200,
        })
        settings = json.loads((self.root / "sample-settings.json").read_text())
        self.assertEqual(settings["fee_basis_points"], {
            "tree_treasury_purchase": 1000, "tree_burn_purchase": 25,
            "reserve": 275, "development": 200,
        })
        self.assertEqual(allocate(10_000), Allocation(8500, 1000, 25, 275, 200))
        self.assertEqual(sum(actual.values()), 1500)

    def test_release_interlock_is_false(self):
        src = (self.root / "move/sources/config.move").read_text()
        self.assertIn("const LIVE_CREATION_ENABLED: bool = false;", src)

    def test_draw_has_private_entry_visibility(self):
        src = (self.root / "move/sources/rounds.move").read_text()
        self.assertRegex(src, r"(?m)^entry fun draw\(")
        self.assertNotRegex(src, r"public(?:\([^)]*\))?\s+(?:entry\s+)?fun draw\(")
        self.assertIn("random::new_generator(randomness, ctx)", src)

    def test_two_transaction_separation_checks_present(self):
        src = (self.root / "move/sources/rounds.move").read_text()
        self.assertIn("round.seal_tx_digest != *ctx.digest()", src)
        self.assertIn("round.draw_tx_digest != *ctx.digest()", src)

    def test_receipt_not_freely_transferable(self):
        src = (self.root / "move/sources/rounds.move").read_text()
        self.assertRegex(src, r"public struct EntryReceipt has key\s*\{")

    def test_buyback_execution_not_claimed_or_exposed(self):
        src = (self.root / "move/sources/buyback.move").read_text()
        self.assertIn("public fun execution_available(): bool { false }", src)
        self.assertNotRegex(src, r"fun (withdraw|execute_buyback|swap|burn)\(")


if __name__ == "__main__":
    unittest.main()
