/// Immutable terms for future rounds. Existing terms have no mutation endpoint.
module tree_pot::config;

use sui::event;
use tree_pot::reserve;

// RELEASE INTERLOCK: deliberately false. This is not a runtime administrator toggle.
// Do not change until every blocker in docs/RELEASE_GATES.md is closed.
const LIVE_CREATION_ENABLED: bool = false;
// Explicit project destinations confirmed by the user; no new admin rights are granted.
const TREE_PURCHASE_WALLET: address = @0x6f1020c2fd6c91129f7cb5e0d651295e87f7245f96b7d090715c89b38197e77f;
const DEVELOPMENT_WALLET: address = @0x18d72fc2a3df6d92d0806da3b04d92be056e2d6d35882a56c16ddb25f48d35d6;
const MAX_PARTICIPANTS: u64 = 128;
const MAX_WINDOW_MS: u64 = 2_592_000_000; // Engineering cap: 30 days, not a launch choice.
const MAX_U64: u64 = 18_446_744_073_709_551_615;

const EReleaseNotEnabled: u64 = 0;
const EInvalidThreshold: u64 = 1;
const EInvalidEntryPrice: u64 = 2;
const EInvalidJoinWindow: u64 = 3;
const EInvalidRecipient: u64 = 4;

public struct AdminCap has key { id: UID }

public struct Configuration has key {
    id: UID,
    entry_mist: u64,
    threshold: u64,
    join_window_ms: u64,
    tree_treasury: address,
    development: address,
    reserve_id: ID,
}

public struct ConfigurationCreated has copy, drop {
    config_id: ID,
    entry_mist: u64,
    threshold: u64,
    join_window_ms: u64,
    tree_treasury: address,
    development: address,
    reserve_id: ID,
}

fun init(ctx: &mut TxContext) {
    let id = object::new(ctx);
    transfer::transfer(AdminCap { id }, ctx.sender());
}

/// Authority only creates new terms. It does not access escrow, draws, or refunds.
entry fun create_configuration(
    _cap: &AdminCap,
    entry_mist: u64,
    threshold: u64,
    join_window_ms: u64,
    ctx: &mut TxContext,
) {
    assert_live_enabled();
    let reserve_id = reserve::new_and_share(ctx);
    let configuration = new_project_configuration(
        entry_mist, threshold, join_window_ms, reserve_id, ctx,
    );
    let tree_treasury = configuration.tree_treasury;
    let development = configuration.development;
    event::emit(ConfigurationCreated {
        config_id: object::id(&configuration),
        entry_mist, threshold, join_window_ms,
        tree_treasury, development, reserve_id,
    });
    transfer::freeze_object(configuration);
}

// Production creation has no caller-supplied fee destination arguments.
fun new_project_configuration(
    entry_mist: u64,
    threshold: u64,
    join_window_ms: u64,
    reserve_id: ID,
    ctx: &mut TxContext,
): Configuration {
    new_configuration(
        entry_mist, threshold, join_window_ms,
        TREE_PURCHASE_WALLET, DEVELOPMENT_WALLET, reserve_id, ctx,
    )
}

fun new_configuration(
    entry_mist: u64,
    threshold: u64,
    join_window_ms: u64,
    tree_treasury: address,
    development: address,
    reserve_id: ID,
    ctx: &mut TxContext,
): Configuration {
    assert!(threshold >= 2 && threshold <= MAX_PARTICIPANTS, EInvalidThreshold);
    assert!(entry_mist > 0 && entry_mist <= MAX_U64 / threshold, EInvalidEntryPrice);
    assert!(join_window_ms > 0 && join_window_ms <= MAX_WINDOW_MS, EInvalidJoinWindow);
    assert!(tree_treasury != @0x0 && development != @0x0, EInvalidRecipient);
    let id = object::new(ctx);
    Configuration {
        id, entry_mist, threshold, join_window_ms,
        tree_treasury, development, reserve_id,
    }
}

public(package) fun assert_live_enabled() {
    assert!(LIVE_CREATION_ENABLED, EReleaseNotEnabled);
}
public fun live_creation_enabled(): bool { LIVE_CREATION_ENABLED }
public fun max_participants(): u64 { MAX_PARTICIPANTS }
public fun entry_mist(c: &Configuration): u64 { c.entry_mist }
public fun threshold(c: &Configuration): u64 { c.threshold }
public fun join_window_ms(c: &Configuration): u64 { c.join_window_ms }
public fun tree_treasury(c: &Configuration): address { c.tree_treasury }
public fun development(c: &Configuration): address { c.development }
public fun reserve_id(c: &Configuration): ID { c.reserve_id }

// Test-only constructors are omitted from a normal production build.
#[test_only]
public fun new_for_testing(
    entry_mist: u64,
    threshold: u64,
    join_window_ms: u64,
    tree_treasury: address,
    development: address,
    reserve_id: ID,
    ctx: &mut TxContext,
): Configuration {
    new_configuration(
        entry_mist, threshold, join_window_ms,
        tree_treasury, development, reserve_id, ctx,
    )
}
#[test_only]
public fun freeze_for_testing(c: Configuration) { transfer::freeze_object(c); }
#[test_only]
public fun assert_live_for_testing() { assert_live_enabled(); }

/// Public inspection only; these functions do not transfer funds or grant authority.
public fun project_treasury_sui_recipient(): address { TREE_PURCHASE_WALLET }
public fun project_development_sui_recipient(): address { DEVELOPMENT_WALLET }

#[test_only]
public fun new_project_for_testing(
    entry_mist: u64,
    threshold: u64,
    join_window_ms: u64,
    reserve_id: ID,
    ctx: &mut TxContext,
): Configuration {
    new_project_configuration(entry_mist, threshold, join_window_ms, reserve_id, ctx)
}
