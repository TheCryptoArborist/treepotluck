/// Authored regression cases. Actual Move execution status is in result.json.
#[test_only]
module tree_pot::boundary_tests;

use std::unit_test::assert_eq;
use sui::clock::Clock;
use sui::test_scenario;
use tree_pot::buyback::BuybackJob;
use tree_pot::config;
use tree_pot::reserve::{Self, ReserveVault};
use tree_pot::rounds::{Self, EntryReceipt, Round};
use tree_pot::test_world as world;

const ENTRY: u64 = 1_000_000_000;

#[test]
fun last_join_before_deadline_seals_and_remains_settleable_after_deadline() {
    let mut s = world::setup(ENTRY, 2, 1000);
    world::join_as(&mut s, @0xA, ENTRY);
    world::set_time(&mut s, 999);
    world::join_as(&mut s, @0xB, ENTRY);
    world::set_time(&mut s, 1000);
    world::draw(&mut s);
    world::settle(&mut s);
    let (phase, count, escrow) = world::state(&mut s);
    assert_eq!(phase, 3);
    assert_eq!(count, 2);
    assert_eq!(escrow, 0);
    s.end();
}

#[test]
fun empty_expired_round_holds_no_player_funds() {
    let mut s = world::setup(ENTRY, 2, 1000);
    world::set_time(&mut s, 1000);
    world::expire(&mut s);
    let (phase, count, escrow) = world::state(&mut s);
    assert_eq!(phase, 4);
    assert_eq!(count, 0);
    assert_eq!(escrow, 0);
    let vault = s.take_shared<ReserveVault>();
    assert_eq!(vault.balance_mist(), 0);
    test_scenario::return_shared(vault);
    s.end();
}

#[test]
fun all_underfilled_entries_remain_individually_refundable_after_expiry() {
    let mut s = world::setup(ENTRY, 3, 1000);
    world::join_as(&mut s, @0xA, ENTRY);
    world::join_as(&mut s, @0xB, ENTRY);
    world::set_time(&mut s, 1000);
    world::exit_as(&mut s, @0xA);
    world::exit_as(&mut s, @0xB);
    assert_eq!(world::coin_balance(&mut s, @0xA), ENTRY);
    assert_eq!(world::coin_balance(&mut s, @0xB), ENTRY);
    let (phase, count, escrow) = world::state(&mut s);
    assert_eq!(phase, 4);
    assert_eq!(count, 0);
    assert_eq!(escrow, 0);
    let vault = s.take_shared<ReserveVault>();
    assert_eq!(vault.balance_mist(), 0);
    test_scenario::return_shared(vault);
    s.end();
}

#[test]
fun removing_tail_preserves_the_first_entry() {
    let mut s = world::setup(ENTRY, 3, 1000);
    world::join_as(&mut s, @0xA, ENTRY);
    world::join_as(&mut s, @0xB, ENTRY);
    world::exit_as(&mut s, @0xB);
    s.next_tx(@0xE0);
    let round = s.take_shared<Round>();
    let (player, _) = round.participant(0);
    assert_eq!(player, @0xA);
    assert!(round.has_entry(@0xA));
    assert!(!round.has_entry(@0xB));
    test_scenario::return_shared(round);
    world::exit_as(&mut s, @0xA);
    assert_eq!(world::coin_balance(&mut s, @0xA), ENTRY);
    s.end();
}

#[test]
fun an_exited_entry_cannot_be_selected_when_remaining_wallets_fill_the_round() {
    let mut s = world::setup(ENTRY, 3, 1000);
    world::join_as(&mut s, @0xA, ENTRY);
    world::join_as(&mut s, @0xB, ENTRY);
    world::exit_as(&mut s, @0xA);
    world::join_as(&mut s, @0xC, ENTRY);
    world::join_as(&mut s, @0xD, ENTRY);
    world::draw(&mut s);
    s.next_tx(@0xE0);
    let round = s.take_shared<Round>();
    let (_, player) = rounds::committed_winner(&round, s.ctx());
    assert!(player == @0xB || player == @0xC || player == @0xD);
    assert!(!round.has_entry(@0xA));
    test_scenario::return_shared(round);
    s.end();
}

#[test]
fun tiny_pot_settlement_keeps_quarter_percent_rounding_consistent() {
    let mut s = world::setup(200, 2, 1000);
    world::join_as(&mut s, @0xA, 200);
    world::join_as(&mut s, @0xB, 200);
    world::draw(&mut s);
    world::settle(&mut s);
    s.next_tx(@0xE0);
    let round = s.take_shared<Round>();
    let (_, winner) = rounds::committed_winner(&round, s.ctx());
    assert_eq!(round.escrow_mist(), 0);
    test_scenario::return_shared(round);
    let job = s.take_shared<BuybackJob>();
    assert_eq!(job.treasury_budget_mist(), 0);
    assert_eq!(job.burn_budget_mist(), 1);
    assert_eq!(job.tree_treasury(), @0xF1);
    test_scenario::return_shared(job);
    let vault = s.take_shared<ReserveVault>();
    assert_eq!(vault.balance_mist(), 11);
    test_scenario::return_shared(vault);
    assert_eq!(world::coin_balance(&mut s, winner), 340);
    assert_eq!(world::coin_balance(&mut s, @0xF1), 40);
    assert_eq!(world::coin_balance(&mut s, @0xF2), 8);
    s.end();
}

#[test]
fun settlement_with_zero_rounded_fees_does_not_reduce_the_prize() {
    let mut s = world::setup(1, 2, 1000);
    world::join_as(&mut s, @0xA, 1);
    world::join_as(&mut s, @0xB, 1);
    world::draw(&mut s);
    world::settle(&mut s);
    s.next_tx(@0xE0);
    let round = s.take_shared<Round>();
    let (_, winner) = rounds::committed_winner(&round, s.ctx());
    test_scenario::return_shared(round);
    let job = s.take_shared<BuybackJob>();
    assert_eq!(job.treasury_budget_mist(), 0);
    assert_eq!(job.burn_budget_mist(), 0);
    test_scenario::return_shared(job);
    assert_eq!(world::coin_balance(&mut s, winner), 2);
    s.end();
}

#[test]
fun retiring_a_settled_receipt_does_not_change_historical_participation() {
    let mut s = world::setup(ENTRY, 2, 1000);
    world::join_as(&mut s, @0xA, ENTRY);
    world::join_as(&mut s, @0xB, ENTRY);
    world::draw(&mut s);
    world::settle(&mut s);
    s.next_tx(@0xA);
    let round = s.take_shared<Round>();
    let receipt = s.take_from_sender<EntryReceipt>();
    rounds::discard_settled_receipt_for_testing(&round, receipt, s.ctx());
    assert_eq!(round.participant_count(), 2);
    assert_eq!(round.escrow_mist(), 0);
    test_scenario::return_shared(round);
    s.next_tx(@0xA);
    assert!(!s.has_most_recent_for_sender<EntryReceipt>());
    s.end();
}

#[test, expected_failure(abort_code = 15, location = rounds)]
fun receipt_cannot_be_retired_while_refundable() {
    let mut s = world::setup(ENTRY, 3, 1000);
    world::join_as(&mut s, @0xA, ENTRY);
    s.next_tx(@0xA);
    let round = s.take_shared<Round>();
    let receipt = s.take_from_sender<EntryReceipt>();
    rounds::discard_settled_receipt_for_testing(&round, receipt, s.ctx());
    test_scenario::return_shared(round);
    s.end();
}

#[test, expected_failure(abort_code = 5, location = rounds)]
fun receipt_from_another_round_is_rejected() {
    let mut s = world::setup(ENTRY, 3, 1000);
    world::join_as(&mut s, @0xA, ENTRY);
    s.next_tx(@0xE0);
    let clock = s.take_shared<Clock>();
    let reserve_id = reserve::create_for_testing(s.ctx());
    let c = config::new_for_testing(ENTRY, 3, 1000, @0xF1, @0xF2, reserve_id, s.ctx());
    rounds::create_for_testing(&c, &clock, s.ctx());
    config::freeze_for_testing(c);
    test_scenario::return_shared(clock);
    // The most recently shared Round is deliberately the second round.
    world::exit_as(&mut s, @0xA);
    s.end();
}

#[test, expected_failure(abort_code = 0, location = rounds)]
fun explicitly_expired_round_cannot_accept_an_entry() {
    let mut s = world::setup(ENTRY, 2, 1000);
    world::set_time(&mut s, 1000);
    world::expire(&mut s);
    world::join_as(&mut s, @0xA, ENTRY);
    s.end();
}

#[test, expected_failure(abort_code = 4, location = rounds)]
fun a_drawn_round_cannot_refund_an_entry() {
    let mut s = world::setup(ENTRY, 2, 1000);
    world::join_as(&mut s, @0xA, ENTRY);
    world::join_as(&mut s, @0xB, ENTRY);
    world::draw(&mut s);
    world::exit_as(&mut s, @0xA);
    s.end();
}

#[test, expected_failure(abort_code = 2, location = rounds)]
fun overpayment_is_rejected_instead_of_silently_charged() {
    let mut s = world::setup(ENTRY, 2, 1000);
    world::join_as(&mut s, @0xA, ENTRY + 1);
    s.end();
}

#[test]
fun maximum_configured_participant_bound_is_accepted() {
    let s = world::setup(ENTRY, 128, 1000);
    s.end();
}

#[test, expected_failure(abort_code = 3, location = config)]
fun excessively_long_join_window_is_rejected() {
    world::setup(ENTRY, 2, 2_592_000_001).end();
}
