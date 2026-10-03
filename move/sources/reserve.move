/// Draft reserve accounting. No withdrawal/governance policy has been authorized.
/// DO NOT enable live rounds until a reviewed reserve policy is implemented.
module tree_pot::reserve;

use sui::balance::{Self, Balance};
use sui::event;
use sui::sui::SUI;

public struct ReserveVault has key {
    id: UID,
    funds: Balance<SUI>,
}

public struct ReserveFunded has copy, drop {
    vault_id: ID,
    round_id: ID,
    amount_mist: u64,
}

public(package) fun new_and_share(ctx: &mut TxContext): ID {
    let id = object::new(ctx);
    let vault = ReserveVault { id, funds: balance::zero() };
    let vault_id = object::id(&vault);
    transfer::share_object(vault);
    vault_id
}

/// Only audited modules in this package can allocate round funds here.
/// Caller must validate the vault ID against the round's fixed configuration.
public(package) fun deposit(vault: &mut ReserveVault, round_id: ID, funds: Balance<SUI>) {
    let amount_mist = funds.value();
    vault.funds.join(funds);
    event::emit(ReserveFunded { vault_id: object::id(vault), round_id, amount_mist });
}

public fun balance_mist(vault: &ReserveVault): u64 { vault.funds.value() }

#[test_only]
public fun create_for_testing(ctx: &mut TxContext): ID { new_and_share(ctx) }
