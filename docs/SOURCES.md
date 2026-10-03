# Import reference record — October 3, 2026

## Requested project sources

- `TREE-Pot-CI-Ready.zip`: prepared CI/wallet-routing source supplied in this conversation. The GitHub import preserves its executable source after UTF-8/LF newline normalization; repository documentation is updated for the actual destination.
- `TREE-Pot-Validated-20261002-223421-864380.zip`: earlier user-uploaded Windows checkpoint with 51-test results. Those results are historical and are not substituted for this revision's CI results.
- User-confirmed purchase wallet, development wallet, 0.25% burn allocation, repository and desired local path in this conversation.

## Current guidance consulted live for this import

- https://github.com/MystenLabs/skills/blob/main/README.md
- https://github.com/MystenLabs/skills/blob/main/sui-move-project/SKILL.md
- https://github.com/MystenLabs/skills/blob/main/sui-build-test/SKILL.md
- https://github.com/MystenLabs/skills/blob/main/move-unit-testing/SKILL.md

These applicable skill files contain inline setup/build/testing guidance. No production contract logic was redesigned during this import. The minimal manifest is retained without overriding built-in mainnet/testnet environment names; the earlier Windows compiler demonstrated that the redundant declaration is rejected.

## Public technical references

- https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow
- https://docs.github.com/en/actions/reference/security/secure-use
- https://git-scm.com/docs/git-clone

The prepared workflow uses these documented patterns. Actual successful execution must be established by a run for the imported GitHub commit, not by this reference record.
