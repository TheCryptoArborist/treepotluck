module boundary_probe::checks;
use tree_pot::rounds::Round;
public fun inspect(round: &Round): u8 { round.phase() }
