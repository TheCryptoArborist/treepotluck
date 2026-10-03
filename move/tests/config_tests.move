#[test_only]
module tree_pot::config_tests;

use std::unit_test::assert_eq;
use tree_pot::config;
use tree_pot::test_world as world;

#[test]
fun live_creation_is_disabled_in_this_release() {
    assert_eq!(config::live_creation_enabled(), false);
}

#[test, expected_failure(abort_code = 0, location = config)]
fun release_interlock_aborts() { config::assert_live_for_testing(); }

// end() handles the unexpected-success path, keeping Scenario (no drop) well-typed.
#[test, expected_failure(abort_code = 1, location = config)]
fun one_participant_configuration_aborts() { world::setup(1_000_000_000, 1, 1000).end(); }

#[test, expected_failure(abort_code = 1, location = config)]
fun oversized_participant_configuration_aborts() { world::setup(1_000_000_000, 129, 1000).end(); }

#[test, expected_failure(abort_code = 2, location = config)]
fun zero_entry_configuration_aborts() { world::setup(0, 2, 1000).end(); }

#[test, expected_failure(abort_code = 2, location = config)]
fun overflowing_pot_configuration_aborts() {
    world::setup(18_446_744_073_709_551_615, 2, 1000).end();
}

#[test, expected_failure(abort_code = 3, location = config)]
fun zero_window_configuration_aborts() { world::setup(1_000_000_000, 2, 0).end(); }
