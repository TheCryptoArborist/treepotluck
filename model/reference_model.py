"""Executable specification, NOT a Move VM, cryptographic RNG, or deployment client.

Draw indices are injected test fixtures. This models state transitions and money
conservation only. It does not validate Sui ownership, bytecode, consensus, gas,
PTB restrictions, DEX pricing, or randomness security.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from enum import IntEnum
from functools import wraps
from typing import Callable, Any

MAX_U64 = (1 << 64) - 1
MAX_PARTICIPANTS = 128
MAX_WINDOW_MS = 30 * 24 * 60 * 60 * 1000
MIST_PER_SUI = 1_000_000_000


class RuleError(ValueError):
    """A modeled abort, not a Move VM error."""


class Phase(IntEnum):
    OPEN = 0
    SEALED = 1
    DRAWN = 2
    SETTLED = 3
    REFUNDING = 4


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuleError(message)


def uint64(value: int) -> int:
    require(type(value) is int and 0 <= value <= MAX_U64, "not_u64")
    return value


def portion(amount: int, bps: int) -> int:
    uint64(amount)
    require(type(bps) is int and 0 <= bps <= 10_000, "invalid_bps")
    # Mirror the overflow-avoiding arithmetic in economics.move.
    whole = uint64((amount // 10_000) * bps)
    fraction = uint64((amount % 10_000) * bps) // 10_000
    return uint64(whole + fraction)


@dataclass(frozen=True)
class Allocation:
    winner: int
    treasury_buyback: int
    burn_buyback: int
    reserve: int
    development: int

    @property
    def total(self) -> int:
        return sum((self.winner, self.treasury_buyback, self.burn_buyback,
                    self.reserve, self.development))


def allocate(gross: int) -> Allocation:
    uint64(gross)
    treasury, burn, reserve, dev = (portion(gross, b) for b in (1000, 25, 275, 200))
    return Allocation(gross - treasury - burn - reserve - dev, treasury, burn, reserve, dev)


@dataclass(frozen=True)
class Config:
    entry: int = MIST_PER_SUI
    threshold: int = 10
    window_ms: int = 24 * 60 * 60 * 1000
    treasury: str = "TEST_TREASURY"
    development: str = "TEST_DEVELOPMENT"
    reserve_id: str = "TEST_RESERVE"

    def __post_init__(self) -> None:
        uint64(self.entry)
        uint64(self.threshold)
        uint64(self.window_ms)
        require(2 <= self.threshold <= MAX_PARTICIPANTS, "invalid_threshold")
        require(0 < self.entry <= MAX_U64 // self.threshold, "invalid_entry")
        require(0 < self.window_ms <= MAX_WINDOW_MS, "invalid_window")
        require(bool(self.treasury) and self.treasury != "0x0", "invalid_treasury")
        require(bool(self.development) and self.development != "0x0", "invalid_development")
        require(bool(self.reserve_id), "invalid_reserve")


@dataclass(frozen=True)
class Receipt:
    id: int
    round_id: str
    player: str
    amount: int


@dataclass(frozen=True)
class PendingBuyback:
    round_id: str
    treasury: str
    treasury_budget: int
    burn_budget: int


# Model atomic rollback of all tracked application state when an operation aborts.
def atomic(method: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(method)
    def wrapped(self: "RoundModel", *args: Any, **kwargs: Any) -> Any:
        before = deepcopy(self.__dict__)
        try:
            result = method(self, *args, **kwargs)
            self.invariants()
            return result
        except Exception:
            self.__dict__.clear()
            self.__dict__.update(before)
            raise
    return wrapped


@dataclass
class RoundModel:
    config: Config = field(default_factory=Config)
    id: str = "ROUND_A"
    opened_at: int = 0
    phase: Phase = Phase.OPEN
    escrow: int = 0
    entries: list[Receipt] = field(default_factory=list)
    by_wallet: dict[str, int] = field(default_factory=dict)
    by_receipt: dict[int, int] = field(default_factory=dict)
    seal_tx: str | None = None
    draw_tx: str | None = None
    selected: int | None = None
    next_receipt: int = 1
    total_deposits: int = 0  # Historical totals can exceed u64 after repeated refunds.
    total_refunds: int = 0
    allocations: Allocation | None = None
    pending_buyback: PendingBuyback | None = None
    treasury_recipient: str | None = None
    treasury_paid_mist: int = 0
    prize_recipient: str | None = None
    development_recipient: str | None = None
    reserve_recipient: str | None = None

    def __post_init__(self) -> None:
        uint64(self.opened_at)
        require(self.opened_at <= MAX_U64 - self.config.window_ms, "deadline_overflow")
        self.invariants()

    @property
    def deadline(self) -> int:
        return self.opened_at + self.config.window_ms

    def invariants(self) -> None:
        n = len(self.entries)
        assert n == len(self.by_wallet) == len(self.by_receipt)
        assert n <= self.config.threshold
        assert len({e.player for e in self.entries}) == n
        for i, e in enumerate(self.entries):
            assert self.by_receipt[e.id] == i
            assert self.by_wallet[e.player] == e.id
            assert e.amount == self.config.entry and e.round_id == self.id
        uint64(self.escrow)
        if self.phase != Phase.SETTLED:
            assert self.escrow == self.config.entry * n
            assert self.allocations is None and self.pending_buyback is None
            assert self.treasury_recipient is None and self.treasury_paid_mist == 0
        else:
            assert self.escrow == 0 and self.allocations is not None
            assert self.allocations.total == self.config.entry * n
            assert self.pending_buyback is not None
            assert self.pending_buyback.treasury_budget == 0
            assert self.treasury_paid_mist == self.allocations.treasury_buyback
            assert self.treasury_recipient == self.config.treasury
            assert self.pending_buyback.burn_budget == self.allocations.burn_buyback
        distributed = self.allocations.total if self.allocations else 0
        assert self.total_deposits == self.total_refunds + self.escrow + distributed
        if self.phase in (Phase.SEALED, Phase.DRAWN, Phase.SETTLED):
            assert n == self.config.threshold and self.seal_tx is not None
        if self.phase in (Phase.DRAWN, Phase.SETTLED):
            assert self.selected is not None and 0 <= self.selected < n
            assert self.draw_tx != self.seal_tx and self.draw_tx is not None
        else:
            assert self.selected is None

    @atomic
    def join(self, player: str, amount: int, now: int, tx: str) -> Receipt:
        uint64(amount)
        uint64(now)
        require(self.phase == Phase.OPEN, "not_open")
        require(now < self.deadline, "deadline_reached")
        require(amount == self.config.entry, "wrong_payment")
        require(player not in self.by_wallet, "duplicate_wallet")
        require(len(self.entries) < self.config.threshold, "full")
        require(bool(tx), "missing_transaction")
        receipt = Receipt(self.next_receipt, self.id, player, amount)
        self.next_receipt += 1
        self.by_wallet[player] = receipt.id
        self.by_receipt[receipt.id] = len(self.entries)
        self.entries.append(receipt)
        self.escrow = uint64(self.escrow + amount)
        self.total_deposits += amount
        if len(self.entries) == self.config.threshold:
            self.phase = Phase.SEALED
            self.seal_tx = tx
        return receipt

    @atomic
    def exit(self, sender: str, receipt: Receipt, now: int) -> int:
        uint64(now)
        require(self.phase in (Phase.OPEN, Phase.REFUNDING), "not_refundable")
        require(receipt.round_id == self.id, "wrong_round")
        require(receipt.player == sender, "not_owner")
        require(receipt.amount == self.config.entry, "wrong_amount")
        require(receipt.id in self.by_receipt, "inactive_receipt")
        require(self.by_wallet.get(sender) == receipt.id, "wrong_receipt")
        index = self.by_receipt[receipt.id]
        require(self.entries[index] == receipt, "wrong_receipt")
        if self.phase == Phase.OPEN and now >= self.deadline:
            self.phase = Phase.REFUNDING
        self.by_receipt.pop(receipt.id)
        self.by_wallet.pop(sender)
        tail = self.entries.pop()
        if index < len(self.entries):
            self.entries[index] = tail
            self.by_receipt[tail.id] = index
        self.escrow -= receipt.amount
        self.total_refunds += receipt.amount
        return receipt.amount

    @atomic
    def expire(self, now: int) -> None:
        uint64(now)
        require(self.phase == Phase.OPEN, "not_open")
        require(now >= self.deadline, "not_expired")
        require(len(self.entries) < self.config.threshold, "not_underfilled")
        self.phase = Phase.REFUNDING

    @atomic
    def record_draw_fixture(self, selected: int, tx: str) -> None:
        """Inject a test outcome. This does NOT simulate or validate a VRF."""
        require(self.phase == Phase.SEALED, "not_sealed")
        require(bool(tx) and tx != self.seal_tx, "separate_transaction_required")
        require(type(selected) is int and 0 <= selected < len(self.entries), "invalid_index")
        self.selected, self.draw_tx, self.phase = selected, tx, Phase.DRAWN

    @atomic
    def settle(self, reserve_id: str, tx: str, *, simulate_abort: bool = False) -> Allocation:
        require(self.phase == Phase.DRAWN, "not_drawn")
        require(bool(tx) and tx != self.draw_tx, "separate_transaction_required")
        require(reserve_id == self.config.reserve_id, "wrong_reserve")
        assert self.selected is not None
        a = allocate(self.escrow)
        self.phase, self.escrow, self.allocations = Phase.SETTLED, 0, a
        self.prize_recipient = self.entries[self.selected].player
        self.treasury_recipient = self.config.treasury
        self.treasury_paid_mist = a.treasury_buyback
        self.development_recipient = self.config.development
        self.reserve_recipient = reserve_id
        self.pending_buyback = PendingBuyback(
            self.id, self.config.treasury, 0, a.burn_buyback)
        # Exercise atomic rollback, not an actual Move transfer failure.
        require(not simulate_abort, "simulated_settlement_abort")
        return a
