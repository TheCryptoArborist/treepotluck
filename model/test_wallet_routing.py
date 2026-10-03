"""Wallet routing model and text checks, not execution of Move bytecode."""
from copy import deepcopy
from pathlib import Path
import json
import re
import unittest

from reference_model import Config, RoundModel, RuleError, MIST_PER_SUI

ROOT = Path(__file__).resolve().parents[1]
PURCHASE = '0x6f1020c2fd6c91129f7cb5e0d651295e87f7245f96b7d090715c89b38197e77f'
DEVELOPMENT = '0x18d72fc2a3df6d92d0806da3b04d92be056e2d6d35882a56c16ddb25f48d35d6'


def sealed_round():
    r = RoundModel(Config(entry=50*MIST_PER_SUI, threshold=2, treasury=PURCHASE,
                          development=DEVELOPMENT, window_ms=1000))
    r.join('a', r.config.entry, 0, 'join_a')
    r.join('b', r.config.entry, 0, 'join_b')
    return r


class WalletRoutingChecks(unittest.TestCase):
    def test_addresses_are_exact_and_full_width(self):
        settings = json.loads((ROOT/'sample-settings.json').read_text())
        self.assertEqual(settings['tree_treasury_address'], PURCHASE)
        self.assertEqual(settings['development_address'], DEVELOPMENT)
        for addr in (PURCHASE, DEVELOPMENT):
            self.assertRegex(addr, r'^0x[0-9a-f]{64}$')
        self.assertEqual(settings['treasury_receives_asset'], '0x2::sui::SUI')
        self.assertFalse(settings['wallet_control_independently_verified'])

    def test_hundred_sui_routes_ten_and_two_not_ten_point_two_five(self):
        r = sealed_round()
        r.record_draw_fixture(0, 'draw')
        a = r.settle(r.config.reserve_id, 'settle')
        self.assertEqual(r.treasury_recipient, PURCHASE)
        self.assertEqual(r.treasury_paid_mist, 10*MIST_PER_SUI)
        self.assertEqual(r.development_recipient, DEVELOPMENT)
        self.assertEqual(a.development, 2*MIST_PER_SUI)
        self.assertEqual(r.pending_buyback.treasury_budget, 0)
        self.assertEqual(r.pending_buyback.burn_budget, 250_000_000)
        self.assertEqual(a.winner, 85*MIST_PER_SUI)
        self.assertEqual(a.reserve, 2_750_000_000)

    def test_no_treasury_payment_on_join_or_draw(self):
        r = sealed_round()
        self.assertIsNone(r.treasury_recipient)
        self.assertEqual(r.treasury_paid_mist, 0)
        r.record_draw_fixture(0, 'draw')
        self.assertIsNone(r.treasury_recipient)
        self.assertEqual(r.treasury_paid_mist, 0)

    def test_aborted_settlement_rolls_back_treasury_payment_in_model(self):
        r = sealed_round()
        r.record_draw_fixture(0, 'draw')
        before = deepcopy(r.__dict__)
        with self.assertRaisesRegex(RuleError, 'simulated_settlement_abort'):
            r.settle(r.config.reserve_id, 'settle', simulate_abort=True)
        self.assertEqual(before, r.__dict__)
        r.settle(r.config.reserve_id, 'retry')
        self.assertEqual(r.treasury_paid_mist, 10*MIST_PER_SUI)

    def test_fee_wallets_do_not_receive_early_refund_amounts(self):
        r = RoundModel(Config(threshold=2, treasury=PURCHASE, development=DEVELOPMENT))
        receipt = r.join('a', r.config.entry, 0, 'join')
        self.assertEqual(r.exit('a', receipt, 0), r.config.entry)
        self.assertIsNone(r.treasury_recipient)
        self.assertEqual(r.treasury_paid_mist, 0)
        self.assertIsNone(r.development_recipient)

    def test_production_configuration_uses_fixed_destinations(self):
        src = (ROOT/'move/sources/config.move').read_text()
        self.assertIn(f'const TREE_PURCHASE_WALLET: address = @{PURCHASE};', src)
        self.assertIn(f'const DEVELOPMENT_WALLET: address = @{DEVELOPMENT};', src)
        args = re.search(r'entry fun create_configuration\((.*?)\)\s*\{', src, re.S).group(1)
        self.assertNotIn('tree_treasury: address', args)
        self.assertNotIn('development: address', args)
        self.assertIn('let configuration = new_project_configuration(', src)
        self.assertIn('TREE_PURCHASE_WALLET, DEVELOPMENT_WALLET, reserve_id, ctx', src)

    def test_settlement_sends_sui_to_round_destinations(self):
        src = (ROOT/'move/sources/rounds.move').read_text()
        self.assertIn('coin::from_balance(treasury_budget, ctx), round.tree_treasury', src)
        self.assertIn('coin::from_balance(development_budget, ctx), round.development', src)
        self.assertIn('balance::zero<SUI>(), burn_budget, ctx', src)
        self.assertIn('event::emit(WalletAllocationsPaid {', src)
        self.assertNotIn('treasury_budget, burn_budget, ctx', src)

    def test_burn_stays_unassigned_and_release_disabled(self):
        settings = json.loads((ROOT/'sample-settings.json').read_text())
        self.assertIsNone(settings['burn_budget_wallet_address'])
        self.assertIsNone(settings['burn_authority_verification'])
        self.assertFalse(settings['live_creation_enabled'])
        self.assertFalse(settings['move_tests_executed'])
        src = (ROOT/'move/sources/buyback.move').read_text()
        self.assertIn('assert!(treasury_budget_mist == 0, ETreasuryBudgetNotZero)', src)
        self.assertIn('public fun execution_available(): bool { false }', src)


if __name__ == '__main__':
    unittest.main()
