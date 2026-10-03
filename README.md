# TREE Pot Luck

SUI-funded, threshold-based winner-selection game for the TREE ecosystem.

**Development only. Not deployed. Live entries remain disabled.**

## Pot allocation

| Destination | Percentage of the completed SUI pot | Treatment |
|---|---:|---|
| Winner | 85% plus integer rounding dust | SUI prize |
| Treasury purchase wallet | 10% | SUI; subsequent TREE purchases are wallet-managed |
| TREE burn-purchase budget | 0.25% | Separate contract escrow; execution pending |
| Reserve | 2.75% | Separate vault; spending policy pending |
| Development | 2% | SUI to the designated development wallet |

Purchase wallet: `0x6f1020c2fd6c91129f7cb5e0d651295e87f7245f96b7d090715c89b38197e77f`

Development wallet: `0x18d72fc2a3df6d92d0806da3b04d92be056e2d6d35882a56c16ddb25f48d35d6`

Receiving fee allocations does not confer administrator authority. The 10% SUI payment is not a contract-enforced TREE swap. The burn budget is not paid to either wallet.

## Project layout

- `move/`: Move 2024 package, contract source and scenario tests.
- `model/`: independent Python accounting/state model and regression checks.
- `scripts/`: checksum-verifying toolchain installer and validation/evidence collection.
- `validation_tests/`: tests of the validation tooling, including synthetic evidence cases.
- `probes/`: external-package positive control and expected compiler rejections.
- `.github/workflows/`: validation only; no wallet credentials or deployment steps.

The source import and GitHub validation setup are being added to this repository. Build status must be read from the Actions run for the specific commit; preparation or older Windows results are not a pass for a new revision.

## Local checkout

Requested Windows location: `D:\Finance\Crypto\Repos\treepotluck`.

```text
git clone https://github.com/TheCryptoArborist/treepotluck.git "D:\Finance\Crypto\Repos\treepotluck"
```

A Windows checkout is separate from the hosted GitHub repository. Cloning does not deploy the game or spend SUI.

## Release gates

Do not enable live entries until the current revision passes compilation and the complete test suite, the burn-purchase mechanism and reserve policy are implemented and approved, adversarial transaction tests are complete, and independent security review and deployment/source verification are complete. Local or CI validation is not a security audit or launch approval.

Before technical changes, consult the current README and applicable skill files at `https://github.com/MystenLabs/skills` rather than relying on a saved snapshot.
