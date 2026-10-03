module boundary_probe::checks;
use sui::clock::Clock;
use tree_pot::config::Configuration;
use tree_pot::rounds;
public fun attempt(configuration: &Configuration, clock: &Clock, ctx: &mut TxContext) {
    rounds::create_for_testing(configuration, clock, ctx);
}
