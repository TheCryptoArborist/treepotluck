/// AUTHORED, NOT EXECUTED in the delivery environment. See docs/TEST_REPORT.md.
#[test_only]
module tree_pot::rounds_tests;

use std::unit_test::assert_eq;
use sui::clock::Clock;
use sui::test_scenario;
use tree_pot::buyback::BuybackJob;
use tree_pot::reserve::{Self, ReserveVault};
use tree_pot::rounds::{Self, EntryReceipt, Round};
use tree_pot::test_world as world;

const ENTRY: u64 = 1_000_000_000;

#[test]
fun entry_is_escrowed_without_fees() {
    let mut s = world::setup(ENTRY, 3, 1000);
    world::join_as(&mut s, @0xA, ENTRY);
    let (phase, n, escrow) = world::state(&mut s);
    assert_eq!(phase, 0);
    assert_eq!(n, 1);
    assert_eq!(escrow, ENTRY);
    s.end();
}

#[test]
fun final_entry_seals_without_drawing() {
    let mut s = world::setup(ENTRY, 2, 1000);
    world::join_as(&mut s, @0xA, ENTRY);
    world::join_as(&mut s, @0xB, ENTRY);
    let (phase, n, escrow) = world::state(&mut s);
    assert_eq!(phase, 1);
    assert_eq!(n, 2);
    assert_eq!(escrow, 2 * ENTRY);
    s.end();
}

#[test]
fun exit_refunds_full_entry_before_deadline() {
    let mut s = world::setup(ENTRY, 3, 1000);
    world::join_as(&mut s, @0xA, ENTRY);
    world::exit_as(&mut s, @0xA);
    assert_eq!(world::coin_balance(&mut s, @0xA), ENTRY);
    let (phase, n, escrow) = world::state(&mut s);
    assert_eq!(phase, 0);
    assert_eq!(n, 0);
    assert_eq!(escrow, 0);
    s.end();
}

#[test]
fun expiry_refund_does_not_require_expire_transaction() {
    let mut s = world::setup(ENTRY, 3, 1000);
    world::join_as(&mut s, @0xA, ENTRY);
    world::set_time(&mut s, 1000);
    world::exit_as(&mut s, @0xA);
    assert_eq!(world::coin_balance(&mut s, @0xA), ENTRY);
    let (phase, n, escrow) = world::state(&mut s);
    assert_eq!(phase, 4);
    assert_eq!(n, 0);
    assert_eq!(escrow, 0);
    s.end();
}

#[test]
fun removing_first_entry_repairs_moved_entry_index() {
    let mut s = world::setup(ENTRY, 4, 1000);
    world::join_as(&mut s, @0xA, ENTRY);
    world::join_as(&mut s, @0xB, ENTRY);
    world::join_as(&mut s, @0xC, ENTRY);
    world::exit_as(&mut s, @0xA);
    world::exit_as(&mut s, @0xC);
    world::exit_as(&mut s, @0xB);
    let (_, n, escrow) = world::state(&mut s);
    assert_eq!(n, 0);
    assert_eq!(escrow, 0);
    s.end();
}

#[test]
fun exited_wallet_can_rejoin_before_closure() {
    let mut s = world::setup(ENTRY, 3, 1000);
    world::join_as(&mut s, @0xA, ENTRY);
    world::exit_as(&mut s, @0xA);
    world::join_as(&mut s, @0xA, ENTRY);
    let (_, n, escrow) = world::state(&mut s);
    assert_eq!(n, 1);
    assert_eq!(escrow, ENTRY);
    s.end();
}

#[test]
fun committed_draw_settles_to_winner_and_fixed_allocations() {
    let mut s = world::setup(ENTRY, 2, 1000);
    world::join_as(&mut s, @0xA, ENTRY);
    world::join_as(&mut s, @0xB, ENTRY);
    world::draw(&mut s);
    world::settle(&mut s);
    s.next_tx(@0xE0);
    let round = s.take_shared<Round>();
    let (index, winner) = rounds::committed_winner(&round, s.ctx());
    assert!(index < 2);
    assert!(winner == @0xA || winner == @0xB);
    assert_eq!(round.phase(), 3);
    assert_eq!(round.escrow_mist(), 0);
    test_scenario::return_shared(round);
    let vault = s.take_shared<ReserveVault>();
    assert_eq!(vault.balance_mist(), 55_000_000);
    test_scenario::return_shared(vault);
    let job = s.take_shared<BuybackJob>();
    assert_eq!(job.treasury_budget_mist(), 0);
    assert_eq!(job.burn_budget_mist(), 5_000_000);
    test_scenario::return_shared(job);
    assert_eq!(world::coin_balance(&mut s, winner), 1_700_000_000);
    assert_eq!(world::coin_balance(&mut s, @0xF1), 200_000_000);
    assert_eq!(world::coin_balance(&mut s, @0xF2), 40_000_000);
    s.end();
}

// Cleanup below each expected abort is an unexpected-success path needed to
// consume the linear Scenario value; it does not mask an expected abort.
#[test, expected_failure(abort_code = 2, location = rounds)]
fun wrong_payment_aborts() {
    let mut s = world::setup(ENTRY, 2, 1000);
    world::join_as(&mut s, @0xA, ENTRY - 1);
    s.end();
}

#[test, expected_failure(abort_code = 3, location = rounds)]
fun duplicate_wallet_aborts() {
    let mut s = world::setup(ENTRY, 3, 1000);
    world::join_as(&mut s, @0xA, ENTRY);
    world::join_as(&mut s, @0xA, ENTRY);
    s.end();
}

#[test, expected_failure(abort_code = 1, location = rounds)]
fun entry_at_exact_deadline_aborts() {
    let mut s = world::setup(ENTRY, 2, 1000);
    world::set_time(&mut s, 1000);
    world::join_as(&mut s, @0xA, ENTRY);
    s.end();
}

#[test, expected_failure(abort_code = 0, location = rounds)]
fun entry_after_threshold_aborts() {
    let mut s = world::setup(ENTRY, 2, 1000);
    world::join_as(&mut s, @0xA, ENTRY);
    world::join_as(&mut s, @0xB, ENTRY);
    world::join_as(&mut s, @0xC, ENTRY);
    s.end();
}

#[test, expected_failure(abort_code = 4, location = rounds)]
fun sealed_round_exit_aborts() {
    let mut s = world::setup(ENTRY, 2, 1000);
    world::join_as(&mut s, @0xA, ENTRY);
    world::join_as(&mut s, @0xB, ENTRY);
    world::exit_as(&mut s, @0xA);
    s.end();
}

#[test, expected_failure(abort_code = 12, location = rounds)]
fun early_expiry_aborts() {
    let mut s = world::setup(ENTRY, 2, 1000);
    world::expire(&mut s);
    s.end();
}

#[test, expected_failure(abort_code = 7, location = rounds)]
fun underfilled_draw_aborts() {
    let mut s = world::setup(ENTRY, 2, 1000);
    world::join_as(&mut s, @0xA, ENTRY);
    world::draw(&mut s);
    s.end();
}

#[test, expected_failure(abort_code = 8, location = rounds)]
fun last_join_and_draw_same_transaction_aborts() {
    let mut s = world::setup(ENTRY, 2, 1000);
    world::join_as(&mut s, @0xA, ENTRY);
    world::join_and_draw_same_tx(&mut s, @0xB, ENTRY);
    s.end();
}

#[test, expected_failure(abort_code = 8, location = rounds)]
fun draw_and_settlement_same_transaction_aborts() {
    let mut s = world::setup(ENTRY, 2, 1000);
    world::join_as(&mut s, @0xA, ENTRY);
    world::join_as(&mut s, @0xB, ENTRY);
    world::draw_and_settle_same_tx(&mut s);
    s.end();
}

#[test, expected_failure(abort_code = 7, location = rounds)]
fun committed_winner_cannot_be_redrawn() {
    let mut s = world::setup(ENTRY, 2, 1000);
    world::join_as(&mut s, @0xA, ENTRY);
    world::join_as(&mut s, @0xB, ENTRY);
    world::draw(&mut s);
    world::draw(&mut s);
    s.end();
}

#[test, expected_failure(abort_code = 9, location = rounds)]
fun settlement_before_draw_aborts() {
    let mut s = world::setup(ENTRY, 2, 1000);
    world::join_as(&mut s, @0xA, ENTRY);
    world::join_as(&mut s, @0xB, ENTRY);
    world::settle(&mut s);
    s.end();
}

#[test, expected_failure(abort_code = 9, location = rounds)]
fun repeated_settlement_aborts() {
    let mut s = world::setup(ENTRY, 2, 1000);
    world::join_as(&mut s, @0xA, ENTRY);
    world::join_as(&mut s, @0xB, ENTRY);
    world::draw(&mut s);
    world::settle(&mut s);
    world::settle(&mut s);
    s.end();
}

#[test, expected_failure(abort_code = 10, location = rounds)]
fun substituted_reserve_vault_aborts() {
    let mut s = world::setup(ENTRY, 2, 1000);
    world::join_as(&mut s, @0xA, ENTRY);
    world::join_as(&mut s, @0xB, ENTRY);
    world::draw(&mut s);
    s.next_tx(@0xD0);
    reserve::create_for_testing(s.ctx());
    // world::settle takes the most recent vault, deliberately the wrong one.
    world::settle(&mut s);
    s.end();
}

#[test, expected_failure(abort_code = 6, location = rounds)]
fun explicit_owner_check_rejects_another_wallets_receipt() {
    let mut s = world::setup(ENTRY, 3, 1000);
    world::join_as(&mut s, @0xA, ENTRY);
    s.next_tx(@0xB);
    // Test harness can bypass ownership to test the independent sender assertion.
    let receipt = s.take_from_address<EntryReceipt>(@0xA);
    let mut round = s.take_shared<Round>();
    let clock = s.take_shared<Clock>();
    rounds::exit_for_testing(&mut round, receipt, &clock, s.ctx());
    test_scenario::return_shared(clock);
    test_scenario::return_shared(round);
    s.end();
}
