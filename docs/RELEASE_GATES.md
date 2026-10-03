# Release gates — live funds prohibited in this draft

`LIVE_CREATION_ENABLED` remains false. Do not toggle it merely because a build or test run passes.

## Required before any live entries

- Compile and execute the complete Move suite for the actual release revision; preserve exact source and dependency evidence. Older Windows or synthetic collector results do not certify a newer revision.
- Implement and review the separate 0.25% burn-purchase executor, approved trade path and enforceable price protection. Verify TREE's actual burn authority. Do not call permanent locking a reduction in reported supply.
- Obtain approval for the 2.75% reserve's purpose, spending authority and constraints; implement and test that policy. The current vault has no withdrawal endpoint.
- Confirm launch entry price, participant threshold and join deadline. The sample 1-SUI/10-participant/24-hour terms are examples, not approved launch terms.
- Disclose that 10% is SUI paid to the purchase wallet and the later TREE purchase is wallet-managed, not enforced by this contract. Verify destination control as appropriate; spelling checks are not proof of control.
- Perform adversarial PTB, gas/resource-limit, transaction-ordering, liveness and randomized-path testing beyond these unit tests. Establish permissionless finalization operations and separately funded gas.
- Complete independent security review, upgrade/immutability policy, deployment/source verification and jurisdiction-specific legal review for the intended paid chance-based launch.

## No implied authority

The purchase and development addresses receive only their disclosed SUI allocations. They are not administrators merely by being recipients. Neither is assigned the burn budget. No document in this repository authorizes a deployment, transfer, reserve expenditure or change to an active round.

A successful CI result closes only the particular compiler/test evidence step it actually ran. It does not close the remaining gates.
