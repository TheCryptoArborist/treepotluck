/// New routing tests. These require a fresh Move VM run; old evidence does not cover them.
#[test_only]
module tree_pot::wallet_routing_tests;

use std::unit_test::assert_eq;
use sui::coin::Coin;
use sui::sui::SUI;
use sui::test_scenario::{Self, Scenario};
use tree_pot::buyback::BuybackJob;
use tree_pot::config;
use tree_pot::reserve::ReserveVault;
use tree_pot::rounds::{Self, Round};
use tree_pot::test_world as world;

const PURCHASE: address = @0x6f1020c2fd6c91129f7cb5e0d651295e87f7245f96b7d090715c89b38197e77f;
const DEVELOPMENT: address = @0x18d72fc2a3df6d92d0806da3b04d92be056e2d6d35882a56c16ddb25f48d35d6;
const ENTRY: u64 = 50_000_000_000;

fun assert_no_fee_wallet_coins(s: &mut Scenario) {
    s.next_tx(PURCHASE);
    assert!(!s.has_most_recent_for_sender<Coin<SUI>>());
    s.next_tx(DEVELOPMENT);
    assert!(!s.has_most_recent_for_sender<Coin<SUI>>());
}

#[test]
fun project_destination_constants_match_confirmed_addresses() {
    assert_eq!(config::project_treasury_sui_recipient(), PURCHASE);
    assert_eq!(config::project_development_sui_recipient(), DEVELOPMENT);
    assert!(!config::live_creation_enabled());
}

#[test]
fun hundred_sui_pot_pays_exact_wallets_and_isolates_burn_budget() {
    let mut s = world::setup_project(ENTRY, 2, 1000);
    world::join_as(&mut s, @0xA, ENTRY);
    world::join_as(&mut s, @0xB, ENTRY);
    world::draw(&mut s);
    world::settle(&mut s);
    s.next_tx(@0xE0);
    let round = s.take_shared<Round>();
    let (_, winner) = rounds::committed_winner(&round, s.ctx());
    assert_eq!(round.escrow_mist(), 0);
    assert_eq!(round.phase(), 3);
    test_scenario::return_shared(round);
    let job = s.take_shared<BuybackJob>();
    assert_eq!(job.treasury_budget_mist(), 0);
    assert_eq!(job.burn_budget_mist(), 250_000_000);
    test_scenario::return_shared(job);
    let vault = s.take_shared<ReserveVault>();
    assert_eq!(vault.balance_mist(), 2_750_000_000);
    test_scenario::return_shared(vault);
    assert_eq!(world::coin_balance(&mut s, PURCHASE), 10_000_000_000);
    assert_eq!(world::coin_balance(&mut s, DEVELOPMENT), 2_000_000_000);
    assert_eq!(world::coin_balance(&mut s, winner), 85_000_000_000);
    s.end();
}

#[test]
fun open_round_and_refund_do_not_pay_either_fee_wallet() {
    let mut s = world::setup_project(ENTRY, 2, 1000);
    world::join_as(&mut s, @0xA, ENTRY);
    assert_no_fee_wallet_coins(&mut s);
    world::exit_as(&mut s, @0xA);
    assert_eq!(world::coin_balance(&mut s, @0xA), ENTRY);
    assert_no_fee_wallet_coins(&mut s);
    s.end();
}

#[test]
fun sealed_and_drawn_rounds_do_not_pay_fee_wallets_before_settlement() {
    let mut s = world::setup_project(ENTRY, 2, 1000);
    world::join_as(&mut s, @0xA, ENTRY);
    world::join_as(&mut s, @0xB, ENTRY);
    assert_no_fee_wallet_coins(&mut s);
    world::draw(&mut s);
    assert_no_fee_wallet_coins(&mut s);
    let (_, _, escrow) = world::state(&mut s);
    assert_eq!(escrow, 2 * ENTRY);
    s.end();
}

#[test]
fun permissionless_settler_receives_no_fee_wallet_payment() {
    let mut s = world::setup_project(ENTRY, 2, 1000);
    world::join_as(&mut s, @0xA, ENTRY);
    world::join_as(&mut s, @0xB, ENTRY);
    world::draw(&mut s);
    world::settle(&mut s); // Fixture calls as 0xD0, not as either recipient.
    s.next_tx(@0xD0);
    assert!(!s.has_most_recent_for_sender<Coin<SUI>>());
    assert_eq!(world::coin_balance(&mut s, PURCHASE), 10_000_000_000);
    assert_eq!(world::coin_balance(&mut s, DEVELOPMENT), 2_000_000_000);
    s.end();
}
