/// Pending burn-purchase SUI only. No DEX trade or TREE supply burn is implemented here.
/// Treasury purchase SUI is paid directly by rounds::settle, not escrowed here.
/// The treasury_budget field remains in this draft layout, but new jobs require zero.
/// tree_treasury records the round's purchase-wallet destination; it grants NO
/// authority over the separate burn budget.
/// This draft has no method to withdraw or redirect these balances.
/// Never enable live round creation with this module in its current state.
module tree_pot::buyback;

use sui::balance::Balance;
use sui::event;
use sui::sui::SUI;

// Treasury SUI must be paid to the purchase wallet, not left in this queue.
const ETreasuryBudgetNotZero: u64 = 0;

public struct BuybackJob has key {
    id: UID,
    round_id: ID,
    config_id: ID,
    tree_treasury: address,
    treasury_budget: Balance<SUI>,
    burn_budget: Balance<SUI>,
}

public struct BuybackQueued has copy, drop {
    job_id: ID,
    round_id: ID,
    config_id: ID,
    tree_treasury: address,
    treasury_budget_mist: u64,
    burn_budget_mist: u64,
}

public(package) fun queue(
    round_id: ID,
    config_id: ID,
    tree_treasury: address,
    treasury_budget: Balance<SUI>,
    burn_budget: Balance<SUI>,
    ctx: &mut TxContext,
): ID {
    let treasury_budget_mist = treasury_budget.value();
    assert!(treasury_budget_mist == 0, ETreasuryBudgetNotZero);
    let burn_budget_mist = burn_budget.value();
    let id = object::new(ctx);
    let job = BuybackJob {
        id, round_id, config_id, tree_treasury,
        treasury_budget, burn_budget,
    };
    let job_id = object::id(&job);
    event::emit(BuybackQueued {
        job_id, round_id, config_id, tree_treasury,
        treasury_budget_mist, burn_budget_mist,
    });
    transfer::share_object(job);
    job_id
}

public fun execution_available(): bool { false }
public fun round_id(job: &BuybackJob): ID { job.round_id }
public fun config_id(job: &BuybackJob): ID { job.config_id }
public fun tree_treasury(job: &BuybackJob): address { job.tree_treasury }
public fun treasury_budget_mist(job: &BuybackJob): u64 { job.treasury_budget.value() }
public fun burn_budget_mist(job: &BuybackJob): u64 { job.burn_budget.value() }
