module boundary_probe::checks;
use sui::random::Random;
use tree_pot::rounds::{Self, Round};
public fun attempt(round: &mut Round, random: &Random, ctx: &mut TxContext) {
    rounds::draw(round, random, ctx);
}
