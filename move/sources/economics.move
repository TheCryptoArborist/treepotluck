/// Integer-only SUI accounting. Every allocation is based on the gross pot.
module tree_pot::economics;

const BPS: u64 = 10_000;
const TREASURY_BPS: u64 = 1_000;
const BURN_BPS: u64 = 25; // 0.25% of the gross SUI pot, not TREE supply.
const RESERVE_BPS: u64 = 275; // Remainder reallocated here; winner stays at 85%.
const DEVELOPMENT_BPS: u64 = 200;

/// Public, stable abort codes are documented in docs/API.md.
const EInvalidBasisPoints: u64 = 0;

public struct Allocation has copy, drop, store {
    winner: u64,
    treasury_buyback: u64,
    burn_buyback: u64,
    reserve: u64,
    development: u64,
}

/// Exactly floor(amount * bps / 10_000), without overflowing an intermediate.
/// With bps <= 10_000, both products and their sum fit into u64.
/// This quotient/remainder form deliberately needs neither floats nor casts.
public fun portion(amount: u64, bps: u64): u64 {
    assert!(bps <= BPS, EInvalidBasisPoints);
    (amount / BPS) * bps + ((amount % BPS) * bps) / BPS
}

public fun allocate(gross: u64): Allocation {
    let treasury_buyback = portion(gross, TREASURY_BPS);
    let burn_buyback = portion(gross, BURN_BPS);
    let reserve = portion(gross, RESERVE_BPS);
    let development = portion(gross, DEVELOPMENT_BPS);
    // The winner receives all integer-rounding dust.
    let winner = gross - treasury_buyback - burn_buyback - reserve - development;
    Allocation { winner, treasury_buyback, burn_buyback, reserve, development }
}

public fun winner(a: &Allocation): u64 { a.winner }
public fun treasury_buyback(a: &Allocation): u64 { a.treasury_buyback }
public fun burn_buyback(a: &Allocation): u64 { a.burn_buyback }
public fun reserve(a: &Allocation): u64 { a.reserve }
public fun development(a: &Allocation): u64 { a.development }
public fun total(a: &Allocation): u64 {
    a.winner + a.treasury_buyback + a.burn_buyback + a.reserve + a.development
}
