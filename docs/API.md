# Draft module API map

This describes the imported development source, not deployed object IDs. Inspect Move source for exact signatures and checks.

- `config`: immutable configuration terms, fixed purchase/development destinations, owned AdminCap and a false live-creation interlock. Production creation has no caller-selected fee recipient arguments.
- `rounds`: `create_round`, `join`, `exit`, `expire`, `draw`, `settle`, `discard_settled_receipt`. Non-public entry endpoints are transaction entry points, not cross-module library calls. Test adapters are test-only.
- `economics`: integer `portion` and `allocate` functions; 1000/25/275/200 fee basis points; winner receives the remainder.
- `buyback`: package-only burn-budget queue, read-only inspection, execution unavailable. Treasury budget must be zero in newly queued jobs.
- `reserve`: package-only vault creation and deposit; no spending endpoint.

## Round phases

`0 OPEN`, `1 SEALED`, `2 DRAWN`, `3 SETTLED`, `4 REFUNDING`.

The final join seals. Draw must use a different transaction digest from seal; settlement must use a different transaction digest from draw. Digests enforce separation and are not randomness sources. Underfilled entries can exit with a full entry refund; sealed/drawn/settled entries cannot.

## Abort codes

`economics`: 0 invalid basis points.

`config`: 0 release not enabled; 1 invalid threshold; 2 invalid entry price; 3 invalid join window; 4 invalid recipient.

`buyback`: 0 nonzero treasury budget.

`rounds`: 0 not open; 1 deadline reached; 2 wrong payment; 3 duplicate wallet; 4 not refundable; 5 wrong receipt; 6 not receipt owner; 7 not sealed; 8 separate transaction required; 9 not drawn; 10 wrong reserve; 11 invariant violation; 12 not expired; 13 no committed winner; 14 deadline overflow; 15 not settled.

Compiler probe failures are separate from these Move runtime abort codes. Four negative probes must fail compilation, while the valid control must succeed.
