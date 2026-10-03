/// Threshold SUI escrow. Draft: compilation and independent review outstanding.
module tree_pot::rounds;

use sui::balance::{Self, Balance};
use sui::clock::Clock;
use sui::coin::{Self, Coin};
use sui::event;
use sui::random::{Self, Random};
use sui::sui::SUI;
use sui::table::{Self, Table};
use tree_pot::buyback;
use tree_pot::config::{Self, Configuration};
use tree_pot::economics;
use tree_pot::reserve::{Self, ReserveVault};

const OPEN: u8 = 0;
const SEALED: u8 = 1;
const DRAWN: u8 = 2;
const SETTLED: u8 = 3;
const REFUNDING: u8 = 4;
const MAX_U64: u64 = 18_446_744_073_709_551_615;

const ENotOpen: u64 = 0;
const EDeadlineReached: u64 = 1;
const EWrongPayment: u64 = 2;
const EDuplicateWallet: u64 = 3;
const ENotRefundable: u64 = 4;
const EWrongReceipt: u64 = 5;
const ENotReceiptOwner: u64 = 6;
const ENotSealed: u64 = 7;
const ESeparateTransactionRequired: u64 = 8;
const ENotDrawn: u64 = 9;
const EWrongReserve: u64 = 10;
const EInvariantViolation: u64 = 11;
const ENotExpired: u64 = 12;
const ENoCommittedWinner: u64 = 13;
const EDeadlineOverflow: u64 = 14;
const ENotSettled: u64 = 15;

public struct EntrySlot has copy, drop, store {
    receipt_id: ID,
    player: address,
}

/// No store: only this module can transfer this receipt. No transfer API is exposed.
public struct EntryReceipt has key {
    id: UID,
    round_id: ID,
    player: address,
    entry_mist: u64,
}

public struct Round has key {
    id: UID,
    config_id: ID,
    entry_mist: u64,
    threshold: u64,
    join_deadline_ms: u64,
    tree_treasury: address,
    development: address,
    reserve_id: ID,
    phase: u8,
    escrow: Balance<SUI>,
    entries: vector<EntrySlot>,
    index_by_receipt: Table<ID, u64>,
    receipt_by_wallet: Table<address, ID>,
    seal_tx_digest: vector<u8>,
    draw_tx_digest: vector<u8>,
    winner_index: u64, // Meaningful only in DRAWN / SETTLED.
}

public struct RoundOpened has copy, drop {
    round_id: ID,
    config_id: ID,
    entry_mist: u64,
    threshold: u64,
    join_deadline_ms: u64,
}
public struct EntryAccepted has copy, drop {
    round_id: ID,
    receipt_id: ID,
    player: address,
    active_entries: u64,
}
public struct EntryRefunded has copy, drop {
    round_id: ID,
    receipt_id: ID,
    player: address,
    amount_mist: u64,
    active_entries: u64,
}
public struct RoundSealed has copy, drop { round_id: ID, entries: u64 }
public struct RoundExpired has copy, drop { round_id: ID, remaining_entries: u64 }
public struct WinnerDrawn has copy, drop { round_id: ID, winner_index: u64 }
/// Payment of SUI budgets, NOT evidence of a TREE purchase or burn.
public struct WalletAllocationsPaid has copy, drop {
    round_id: ID,
    treasury_recipient: address,
    treasury_sui_mist: u64,
    development_recipient: address,
    development_sui_mist: u64,
}
public struct RoundSettled has copy, drop {
    round_id: ID,
    winner: address,
    winning_receipt_id: ID,
    gross_mist: u64,
    prize_mist: u64,
    treasury_buyback_mist: u64,
    burn_buyback_mist: u64,
    reserve_mist: u64,
    development_mist: u64,
    buyback_job_id: ID,
}

/// Permissionless using an authentic, immutable configuration; release-gated.
entry fun create_round(configuration: &Configuration, clock: &Clock, ctx: &mut TxContext) {
    config::assert_live_enabled();
    let round = new_round(configuration, clock, ctx);
    emit_opened(&round);
    transfer::share_object(round);
}

fun new_round(configuration: &Configuration, clock: &Clock, ctx: &mut TxContext): Round {
    let now = clock.timestamp_ms();
    let window = configuration.join_window_ms();
    assert!(now <= MAX_U64 - window, EDeadlineOverflow);
    let id = object::new(ctx);
    Round {
        id,
        config_id: object::id(configuration),
        entry_mist: configuration.entry_mist(),
        threshold: configuration.threshold(),
        join_deadline_ms: now + window,
        tree_treasury: configuration.tree_treasury(),
        development: configuration.development(),
        reserve_id: configuration.reserve_id(),
        phase: OPEN,
        escrow: balance::zero(),
        entries: vector[],
        index_by_receipt: table::new(ctx),
        receipt_by_wallet: table::new(ctx),
        seal_tx_digest: vector[],
        draw_tx_digest: vector[],
        winner_index: 0,
    }
}

fun emit_opened(round: &Round) {
    event::emit(RoundOpened {
        round_id: object::id(round), config_id: round.config_id,
        entry_mist: round.entry_mist, threshold: round.threshold,
        join_deadline_ms: round.join_deadline_ms,
    });
}

/// Exact-value payment. Split the wallet's SUI coin before this call.
/// The final accepted entry seals the round but never selects a winner.
entry fun join(round: &mut Round, payment: Coin<SUI>, clock: &Clock, ctx: &mut TxContext) {
    assert!(round.phase == OPEN, ENotOpen);
    assert!(clock.timestamp_ms() < round.join_deadline_ms, EDeadlineReached);
    assert!(payment.value() == round.entry_mist, EWrongPayment);
    let player = ctx.sender();
    assert!(!table::contains(&round.receipt_by_wallet, player), EDuplicateWallet);
    let index = round.entries.length();
    assert!(index < round.threshold, EInvariantViolation);
    assert_escrow(round);

    let id = object::new(ctx);
    let receipt = EntryReceipt {
        id, round_id: object::id(round), player, entry_mist: round.entry_mist,
    };
    let receipt_id = object::id(&receipt);
    round.escrow.join(payment.into_balance());
    table::add(&mut round.index_by_receipt, receipt_id, index);
    table::add(&mut round.receipt_by_wallet, player, receipt_id);
    round.entries.push_back(EntrySlot { receipt_id, player });
    let active_entries = round.entries.length();
    event::emit(EntryAccepted { round_id: object::id(round), receipt_id, player, active_entries });
    transfer::transfer(receipt, player);

    if (active_entries == round.threshold) {
        round.phase = SEALED;
        round.seal_tx_digest = *ctx.digest();
        event::emit(RoundSealed { round_id: object::id(round), entries: active_entries });
    };
    assert_escrow(round);
}

/// Available both before expiry (while underfilled) and after underfilled expiry.
/// No administrative call, fee deduction, or arbitrary refund address is needed.
entry fun exit(round: &mut Round, receipt: EntryReceipt, clock: &Clock, ctx: &mut TxContext) {
    assert!(round.phase == OPEN || round.phase == REFUNDING, ENotRefundable);
    assert_escrow(round);
    let receipt_id = object::id(&receipt);
    assert!(receipt.round_id == object::id(round), EWrongReceipt);
    assert!(receipt.player == ctx.sender(), ENotReceiptOwner);
    assert!(receipt.entry_mist == round.entry_mist, EWrongReceipt);
    assert!(table::contains(&round.index_by_receipt, receipt_id), EWrongReceipt);
    assert!(table::contains(&round.receipt_by_wallet, receipt.player), EWrongReceipt);
    assert!(*table::borrow(&round.receipt_by_wallet, receipt.player) == receipt_id, EWrongReceipt);
    let index = *table::borrow(&round.index_by_receipt, receipt_id);
    assert!(index < round.entries.length(), EInvariantViolation);
    let slot = round.entries[index];
    assert!(slot.receipt_id == receipt_id && slot.player == receipt.player, EWrongReceipt);

    if (round.phase == OPEN && clock.timestamp_ms() >= round.join_deadline_ms) {
        round.phase = REFUNDING;
        event::emit(RoundExpired {
            round_id: object::id(round), remaining_entries: round.entries.length(),
        });
    };

    table::remove(&mut round.index_by_receipt, receipt_id);
    table::remove(&mut round.receipt_by_wallet, receipt.player);
    round.entries.swap_remove(index);
    // Keep the index of the element moved from the vector's tail consistent.
    if (index < round.entries.length()) {
        let moved_receipt = round.entries[index].receipt_id;
        *table::borrow_mut(&mut round.index_by_receipt, moved_receipt) = index;
    };
    let amount_mist = round.entry_mist;
    let player = receipt.player;
    let refund = coin::from_balance(round.escrow.split(amount_mist), ctx);
    let EntryReceipt { id, .. } = receipt;
    id.delete();
    assert_escrow(round);
    event::emit(EntryRefunded {
        round_id: object::id(round), receipt_id, player,
        amount_mist, active_entries: round.entries.length(),
    });
    transfer::public_transfer(refund, player);
}

entry fun expire(round: &mut Round, clock: &Clock) {
    assert!(round.phase == OPEN, ENotOpen);
    assert!(clock.timestamp_ms() >= round.join_deadline_ms, ENotExpired);
    assert!(round.entries.length() < round.threshold, EInvariantViolation);
    round.phase = REFUNDING;
    event::emit(RoundExpired {
        round_id: object::id(round), remaining_entries: round.entries.length(),
    });
}

/// Non-public randomness endpoint. NO winner-dependent transfer, table read,
/// object creation, callback, or branch after selection. Validate before sampling.
entry fun draw(round: &mut Round, randomness: &Random, ctx: &mut TxContext) {
    assert!(round.phase == SEALED, ENotSealed);
    assert!(round.seal_tx_digest != *ctx.digest(), ESeparateTransactionRequired);
    let count = round.entries.length();
    assert!(count == round.threshold && count >= 2, EInvariantViolation);
    assert_escrow(round);

    let mut generator = random::new_generator(randomness, ctx);
    let winner_index = generator.generate_u64_in_range(0, count - 1);
    round.winner_index = winner_index;
    round.draw_tx_digest = *ctx.digest();
    round.phase = DRAWN;
    event::emit(WinnerDrawn { round_id: object::id(round), winner_index });
}

/// A second transaction must settle a previously committed draw.
/// Caller supplies neither a winning index nor payment destinations.
entry fun settle(round: &mut Round, vault: &mut ReserveVault, ctx: &mut TxContext) {
    assert!(round.phase == DRAWN, ENotDrawn);
    assert!(round.draw_tx_digest != *ctx.digest(), ESeparateTransactionRequired);
    assert!(object::id(vault) == round.reserve_id, EWrongReserve);
    assert!(round.entries.length() == round.threshold, EInvariantViolation);
    assert!(round.winner_index < round.entries.length(), EInvariantViolation);
    assert_escrow(round);

    let selected = round.entries[round.winner_index];
    let round_id = object::id(round);
    let gross_mist = round.escrow.value();
    let a = economics::allocate(gross_mist);
    let prize_mist = a.winner();
    let treasury_buyback_mist = a.treasury_buyback();
    let burn_buyback_mist = a.burn_buyback();
    let reserve_mist = a.reserve();
    let development_mist = a.development();

    // All changes/transfers below commit atomically, or none of them do.
    round.phase = SETTLED;
    let prize = round.escrow.split(prize_mist);
    let treasury_budget = round.escrow.split(treasury_buyback_mist);
    let burn_budget = round.escrow.split(burn_buyback_mist);
    let reserve_budget = round.escrow.split(reserve_mist);
    let development_budget = round.escrow.split(development_mist);
    assert!(round.escrow.value() == 0, EInvariantViolation);

    let buyback_job_id = buyback::queue(
        round_id, round.config_id, round.tree_treasury,
        balance::zero<SUI>(), burn_budget, ctx,
    );
    // The 10% treasury allocation leaves as SUI. A later TREE purchase is
    // wallet-managed and is not enforced or certified by this contract.
    transfer::public_transfer(coin::from_balance(treasury_budget, ctx), round.tree_treasury);
    reserve::deposit(vault, round_id, reserve_budget);
    transfer::public_transfer(coin::from_balance(prize, ctx), selected.player);
    transfer::public_transfer(coin::from_balance(development_budget, ctx), round.development);
    event::emit(WalletAllocationsPaid {
        round_id,
        treasury_recipient: round.tree_treasury,
        treasury_sui_mist: treasury_buyback_mist,
        development_recipient: round.development,
        development_sui_mist: development_mist,
    });
    event::emit(RoundSettled {
        round_id, winner: selected.player, winning_receipt_id: selected.receipt_id,
        gross_mist, prize_mist, treasury_buyback_mist, burn_buyback_mist,
        reserve_mist, development_mist, buyback_job_id,
    });
}

/// Optional receipt cleanup after settlement. Historical round entries are retained.
entry fun discard_settled_receipt(round: &Round, receipt: EntryReceipt, ctx: &TxContext) {
    assert!(round.phase == SETTLED, ENotSettled);
    assert!(receipt.round_id == object::id(round), EWrongReceipt);
    assert!(receipt.player == ctx.sender(), ENotReceiptOwner);
    let EntryReceipt { id, .. } = receipt;
    id.delete();
}

fun assert_escrow(round: &Round) {
    assert!(round.escrow.value() == round.entry_mist * round.entries.length(), EInvariantViolation);
}

public fun phase(round: &Round): u8 { round.phase }
public fun entry_mist(round: &Round): u64 { round.entry_mist }
public fun threshold(round: &Round): u64 { round.threshold }
public fun participant_count(round: &Round): u64 { round.entries.length() }
public fun escrow_mist(round: &Round): u64 { round.escrow.value() }
public fun join_deadline_ms(round: &Round): u64 { round.join_deadline_ms }
public fun config_id(round: &Round): ID { round.config_id }
public fun reserve_id(round: &Round): ID { round.reserve_id }
public fun has_entry(round: &Round, player: address): bool {
    table::contains(&round.receipt_by_wallet, player)
}
public fun participant(round: &Round, index: u64): (address, ID) {
    let entry = round.entries[index];
    (entry.player, entry.receipt_id)
}
public fun committed_winner(round: &Round, ctx: &TxContext): (u64, address) {
    assert!(round.phase == DRAWN || round.phase == SETTLED, ENoCommittedWinner);
    assert!(round.draw_tx_digest != *ctx.digest(), ESeparateTransactionRequired);
    (round.winner_index, round.entries[round.winner_index].player)
}
public fun receipt_round_id(receipt: &EntryReceipt): ID { receipt.round_id }
public fun receipt_player(receipt: &EntryReceipt): address { receipt.player }

// These adapters are absent from production bytecode, not privileged live endpoints.
#[test_only]
public fun create_for_testing(c: &Configuration, clock: &Clock, ctx: &mut TxContext) {
    let round = new_round(c, clock, ctx);
    emit_opened(&round);
    transfer::share_object(round);
}
#[test_only]
public fun join_for_testing(round: &mut Round, payment: Coin<SUI>, clock: &Clock, ctx: &mut TxContext) {
    join(round, payment, clock, ctx);
}
#[test_only]
public fun exit_for_testing(round: &mut Round, receipt: EntryReceipt, clock: &Clock, ctx: &mut TxContext) {
    exit(round, receipt, clock, ctx);
}
#[test_only]
public fun expire_for_testing(round: &mut Round, clock: &Clock) { expire(round, clock); }
#[test_only]
public fun draw_for_testing(round: &mut Round, scenario: &mut sui::test_scenario::Scenario) {
    let randomness = sui::test_scenario::take_shared<Random>(scenario);
    draw(round, &randomness, scenario.ctx());
    sui::test_scenario::return_shared(randomness);
}
#[test_only]
public fun settle_for_testing(round: &mut Round, vault: &mut ReserveVault, ctx: &mut TxContext) {
    settle(round, vault, ctx);
}
#[test_only]
public fun create_live_for_testing(c: &Configuration, clock: &Clock, ctx: &mut TxContext) {
    create_round(c, clock, ctx);
}

/// Test-only adapter for checking receipt retirement; absent from normal builds.
#[test_only]
public fun discard_settled_receipt_for_testing(round: &Round, receipt: EntryReceipt, ctx: &TxContext) {
    discard_settled_receipt(round, receipt, ctx);
}
