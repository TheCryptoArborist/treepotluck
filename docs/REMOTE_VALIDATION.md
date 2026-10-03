# GitHub-hosted validation

Repository: https://github.com/TheCryptoArborist/treepotluck

The October 3, 2026 import includes the prepared wallet-routing revision and validation workflow. GitHub Actions is the build runner; no desktop relay is required for future compiler logs. Source is imported as UTF-8 with LF newlines. Historical local preparation logs are not imported as evidence of a new GitHub execution.

## What the workflow does

1. Check out the commit being tested without persisting credentials.
2. Run the independent Python model/source tests and validation-tool tests.
3. Download the pinned mainnet-v1.80.1 Sui release archive and verify its size and SHA256.
4. Run `sui move build --build-env mainnet` on a fresh temporary package copy.
5. Preserve the five production modules and generated dependency Move.lock.
6. Run `sui move test --build-env mainnet --coverage`; require every authored test to pass.
7. Build a valid external-package control, then verify four expected compiler rejections: receipt public-transfer, private escrow access, private draw access, and test-only helper access in a normal build.
8. Recheck source, log, bytecode, dependency-lock and test-count consistency. Export only this invocation's returned evidence directory.

`PASSED_LOCAL_VALIDATION_ONLY` is the successful validator status even on a hosted runner. It means build/test validation, not mainnet deployment, live-fund safety certification, an independent audit, or production-randomness fairness proof.

## Evidence and permissions

The uploaded artifact is named `pot-luck-validation-<run-id>-<attempt>` and contains `ci-context.json`, a summary and this run's `validation/result.json` and logs. Failed runs are preserved too. The collector records a small allowlist of GitHub metadata and checks checkout HEAD against GITHUB_SHA; it does not dump environment secrets.

The workflow has read-only repository permissions, full-commit-pinned actions, no `pull_request_target`, no wallet secrets, and no publication or transfer commands. It does not edit the repository. These measures do not defend against every malicious change to the source or validator; review both.

The exact source commit, not a later README update, is the identity of a tested revision. A checksum against pinned metadata does not independently attest how a binary was built. The recorded release is pinned for reproducibility, not a claim that it will always be the latest mainnet version.

The compiler download exceeds 1 GB on Linux. Download failures and timeouts must remain failures/blockages; never skip checks to produce a green badge. No process in this workflow enables live creation.

## Windows checkout

The user requested `D:\Finance\Crypto\Repos\treepotluck`. Writing this repository on GitHub does not create that local directory. Direct local setup requires authorized filesystem/terminal access to the user's computer.
