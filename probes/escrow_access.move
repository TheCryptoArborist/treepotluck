module boundary_probe::checks;
use tree_pot::rounds::Round;
public fun attempt(round: &Round): u64 { round.escrow.value() }
