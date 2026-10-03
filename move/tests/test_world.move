/// Shared fixtures. No part of this module is published in a normal build.
#[test_only]
module tree_pot::test_world;

use sui::clock::{Self, Clock};
use sui::coin::{Self, Coin};
use sui::random::{Self, Random};
use sui::sui::SUI;
use sui::test_scenario::{Self, Scenario};
use tree_pot::config;
use tree_pot::reserve::{Self, ReserveVault};
use tree_pot::rounds::{Self, EntryReceipt, Round};

public fun setup(entry: u64, threshold: u64, window: u64): Scenario {
    let mut s = test_scenario::begin(@0x0);
    random::create_for_testing(s.ctx());
    let clock = clock::create_for_testing(s.ctx());
    let reserve_id = reserve::create_for_testing(s.ctx());
    let c = config::new_for_testing(entry, threshold, window, @0xF1, @0xF2, reserve_id, s.ctx());
    rounds::create_for_testing(&c, &clock, s.ctx());
    config::freeze_for_testing(c);
    clock::share_for_testing(clock);
    s.next_tx(@0x0);
    let mut r = s.take_shared<Random>();
    // Deterministic fixture bytes only; never a live randomness provider.
    random::update_randomness_state_for_testing(&mut r, 0, vector[7, 3, 1, 9], s.ctx());
    test_scenario::return_shared(r);
    s
}

public fun join_as(s: &mut Scenario, player: address, amount: u64) {
    s.next_tx(player);
    let mut round = s.take_shared<Round>();
    let clock = s.take_shared<Clock>();
    let payment = coin::mint_for_testing<SUI>(amount, s.ctx());
    rounds::join_for_testing(&mut round, payment, &clock, s.ctx());
    test_scenario::return_shared(clock);
    test_scenario::return_shared(round);
}

public fun exit_as(s: &mut Scenario, player: address) {
    s.next_tx(player);
    let receipt = s.take_from_sender<EntryReceipt>();
    let mut round = s.take_shared<Round>();
    let clock = s.take_shared<Clock>();
    rounds::exit_for_testing(&mut round, receipt, &clock, s.ctx());
    test_scenario::return_shared(clock);
    test_scenario::return_shared(round);
}

public fun set_time(s: &mut Scenario, timestamp: u64) {
    s.next_tx(@0x0);
    let mut clock = s.take_shared<Clock>();
    clock::set_for_testing(&mut clock, timestamp);
    test_scenario::return_shared(clock);
}

public fun expire(s: &mut Scenario) {
    s.next_tx(@0xD0);
    let mut round = s.take_shared<Round>();
    let clock = s.take_shared<Clock>();
    rounds::expire_for_testing(&mut round, &clock);
    test_scenario::return_shared(clock);
    test_scenario::return_shared(round);
}

public fun draw(s: &mut Scenario) {
    s.next_tx(@0xD0);
    let mut round = s.take_shared<Round>();
    rounds::draw_for_testing(&mut round, s);
    test_scenario::return_shared(round);
}

public fun settle(s: &mut Scenario) {
    s.next_tx(@0xD0);
    let mut round = s.take_shared<Round>();
    let mut vault = s.take_shared<ReserveVault>();
    rounds::settle_for_testing(&mut round, &mut vault, s.ctx());
    test_scenario::return_shared(vault);
    test_scenario::return_shared(round);
}

public fun state(s: &mut Scenario): (u8, u64, u64) {
    s.next_tx(@0xE0);
    let round = s.take_shared<Round>();
    let (phase, count, escrow) = (round.phase(), round.participant_count(), round.escrow_mist());
    test_scenario::return_shared(round);
    (phase, count, escrow)
}

public fun coin_balance(s: &mut Scenario, player: address): u64 {
    s.next_tx(player);
    let coin = s.take_from_sender<Coin<SUI>>();
    let value = coin.value();
    s.return_to_sender(coin);
    value
}

public fun join_and_draw_same_tx(s: &mut Scenario, player: address, amount: u64) {
    s.next_tx(player);
    let mut round = s.take_shared<Round>();
    let clock = s.take_shared<Clock>();
    let payment = coin::mint_for_testing<SUI>(amount, s.ctx());
    rounds::join_for_testing(&mut round, payment, &clock, s.ctx());
    rounds::draw_for_testing(&mut round, s);
    test_scenario::return_shared(clock);
    test_scenario::return_shared(round);
}

public fun draw_and_settle_same_tx(s: &mut Scenario) {
    s.next_tx(@0xD0);
    let mut round = s.take_shared<Round>();
    let mut vault = s.take_shared<ReserveVault>();
    rounds::draw_for_testing(&mut round, s);
    rounds::settle_for_testing(&mut round, &mut vault, s.ctx());
    test_scenario::return_shared(vault);
    test_scenario::return_shared(round);
}

/// Test-only fixture using the exact project recipient constructor.
public fun setup_project(entry: u64, threshold: u64, window: u64): Scenario {
    let mut s = test_scenario::begin(@0x0);
    random::create_for_testing(s.ctx());
    let clock = clock::create_for_testing(s.ctx());
    let reserve_id = reserve::create_for_testing(s.ctx());
    let c = config::new_project_for_testing(entry, threshold, window, reserve_id, s.ctx());
    rounds::create_for_testing(&c, &clock, s.ctx());
    config::freeze_for_testing(c);
    clock::share_for_testing(clock);
    s.next_tx(@0x0);
    let mut r = s.take_shared<Random>();
    // Deterministic fixture bytes only; never a live randomness provider.
    random::update_randomness_state_for_testing(&mut r, 0, vector[7, 3, 1, 9], s.ctx());
    test_scenario::return_shared(r);
    s
}

