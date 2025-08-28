# =======================================
# Provided by Akuna (challenge framework)
# Do not edit
# =======================================

import abc
import random
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import Enum, auto
from typing import Any


class OptionType(Enum):
    CALL = auto()
    PUT = auto()

    def __str__(self) -> str:
        return "C" if self is OptionType.CALL else "P"


@dataclass(eq=True, frozen=True, unsafe_hash=True)
class Option:
    option_id: int
    option_type: OptionType
    steps_until_expiry: int
    strike: int
    underlying_id: int
    underlying_name: str

    def __post_init__(self) -> None:
        if self.steps_until_expiry < 0:
            raise ValueError("Steps until expiry must be non-negative")

    def __str__(self) -> str:
        return f"{self.option_id} ({self.steps_until_expiry}s {self.underlying_name} {self.strike}{self.option_type!s})"

    @classmethod
    def from_underlying(
        cls: type["Option"],
        underlying: "Underlying",
        option_id: int,
        option_type: OptionType,
        steps_until_expiry: int,
        strike: int,
    ) -> "Option":
        return Option(
            option_id=option_id,
            option_type=option_type,
            steps_until_expiry=steps_until_expiry,
            strike=strike,
            underlying_id=underlying.underlying_id,
            underlying_name=underlying.name,
        )

    def advance_step(self) -> "Option":
        if self.steps_until_expiry == 0:
            return self

        return replace(self, steps_until_expiry=self.steps_until_expiry - 1)

    def contract_matches(self, other: "Option") -> bool:
        return replace(other, option_id=self.option_id) == self

    def expiry_valuation(self, underlying_valuation: float) -> float:
        if self.option_type == OptionType.CALL:
            return max(0, underlying_valuation - self.strike)
        return max(0, self.strike - underlying_valuation)


class Position:
    def __init__(self) -> None:
        self.option_quantity_by_option_id: dict[int, int] = defaultdict(int)
        self.underlying_quantity_by_underlying_id: dict[int, float] = defaultdict(float)

    def add_option_quantity(self, option_id: int, quantity: int) -> None:
        self.option_quantity_by_option_id[option_id] += quantity

    def add_underlying_quantity(self, underlying_id: int, quantity: float) -> None:
        quantity = round(quantity, 2)
        self.underlying_quantity_by_underlying_id[underlying_id] += quantity


@dataclass(frozen=True)
class Underlying:
    name: str
    underlying_id: int

    valuation: float

    down_move_probability: float
    down_move_step: float
    noise_std_dev: float
    up_move_probability: float
    up_move_step: float

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Underlying):
            return False
        return self.underlying_id == other.underlying_id

    def __post_init__(self) -> None:
        if self.down_move_step <= 0 or self.up_move_step <= 0:
            raise ValueError("Down/up move steps must both be positive")

        if self.down_move_probability <= 0 or self.up_move_probability <= 0:
            raise ValueError("Down/up move probabilities must both be positive")

        if self.down_move_probability + self.up_move_probability != 1:
            raise ValueError("Down and up move probabilities must sum to 1")

        if ((self.down_move_probability * self.down_move_step) - (self.up_move_probability * self.up_move_step)) > 1e-5:
            raise ValueError("Underlying has drift")

    def advance_step(self) -> "Underlying":
        if random.random() < self.up_move_probability:
            valuation: float = self.valuation + self.up_move_step
        else:
            valuation = self.valuation - self.down_move_step

        valuation += random.gauss(sigma=self.noise_std_dev)
        valuation = max(valuation, 0)
        return replace(self, valuation=round(valuation, 2))


class BaseMarketMaker:
    def __init__(self, underlying_initial_state: list[Underlying], option_initial_state: list[Option]) -> None:
        self.underlying_state: list[Underlying] = underlying_initial_state
        self.active_option_state: list[Option] = option_initial_state
        self.position: Position = Position()

    @property
    @abc.abstractmethod
    def name(self) -> str: ...

    def buy_underlying(self, underlying_id: int, quantity: float) -> None:
        if quantity <= 0:
            raise ValueError("Trade quantity must be positive")

        self.trade_underlying_callback(underlying_id, quantity)
        self.position.add_underlying_quantity(underlying_id, quantity)

    @abc.abstractmethod
    def make_market(self, option: Option) -> tuple[float, float]: ...

    def on_bid_hit(self, option: Option, bid_price: float) -> None:
        self.position.add_option_quantity(option.option_id, 1)

    def on_offer_hit(self, option: Option, offer_price: float) -> None:
        self.position.add_option_quantity(option.option_id, -1)

    def on_step_advance(self, new_underlying_state: list[Underlying], new_option_state: list[Option]) -> None:
        self.underlying_state = new_underlying_state
        self.active_option_state = new_option_state

    def register_trade_underlying_callback(self, trade_underlying_callback: Callable[[int, float], None]) -> None:
        self.trade_underlying_callback = trade_underlying_callback

    @abc.abstractmethod
    def price_option(self, option: Option) -> float: ...

    def sell_underlying(self, underlying_id: int, quantity: float) -> None:
        if quantity <= 0:
            raise ValueError("Trade quantity must be positive")

        self.trade_underlying_callback(underlying_id, -quantity)
        self.position.add_underlying_quantity(underlying_id, -quantity)