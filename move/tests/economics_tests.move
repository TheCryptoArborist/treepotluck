#[test_only]
module tree_pot::economics_tests;

use std::unit_test::assert_eq;
use tree_pot::economics;

#[test]
fun ten_sui_pot_is_split_exactly() {
    let a = economics::allocate(10_000_000_000);
    assert_eq!(a.winner(), 8_500_000_000);
    assert_eq!(a.treasury_buyback(), 1_000_000_000);
    assert_eq!(a.burn_buyback(), 25_000_000);
    assert_eq!(a.reserve(), 275_000_000);
    assert_eq!(a.development(), 200_000_000);
    assert_eq!(a.total(), 10_000_000_000);
}

#[test]
fun one_hundred_sui_pot_funds_ten_and_quarter_sui_buyback() {
    let a = economics::allocate(100_000_000_000);
    assert_eq!(a.winner(), 85_000_000_000);
    assert_eq!(a.treasury_buyback() + a.burn_buyback(), 10_250_000_000);
}

#[test]
fun zero_gross_is_conserved() { assert_eq!(economics::allocate(0).total(), 0); }

#[test]
fun winner_receives_rounding_dust() {
    let a = economics::allocate(10_003);
    assert_eq!(a.winner(), 8_503);
    assert_eq!(a.total(), 10_003);
    assert_eq!(economics::allocate(1).winner(), 1);
}

#[test]
fun maximum_u64_does_not_overflow_fee_products() {
    let max = 18_446_744_073_709_551_615;
    assert_eq!(economics::allocate(max).total(), max);
    assert_eq!(economics::portion(max, 10_000), max);
}

#[test, expected_failure(abort_code = 0, location = economics)]
fun basis_points_above_one_hundred_percent_abort() {
    economics::portion(100, 10_001);
}

#[test]
fun quarter_percent_burn_rounds_down_in_small_pots() {
    assert_eq!(economics::allocate(399).burn_buyback(), 0);
    let a = economics::allocate(400);
    assert_eq!(a.burn_buyback(), 1);
    assert_eq!(a.reserve(), 11);
    assert_eq!(a.winner(), 340);
    assert_eq!(a.total(), 400);
}

#[test]
fun one_thousand_sui_pot_uses_quarter_percent_burn() {
    let a = economics::allocate(1_000_000_000_000);
    assert_eq!(a.winner(), 850_000_000_000);
    assert_eq!(a.treasury_buyback(), 100_000_000_000);
    assert_eq!(a.burn_buyback(), 2_500_000_000);
    assert_eq!(a.reserve(), 27_500_000_000);
    assert_eq!(a.development(), 20_000_000_000);
    assert_eq!(a.total(), 1_000_000_000_000);
}
