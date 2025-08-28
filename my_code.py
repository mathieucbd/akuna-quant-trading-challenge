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


# ================================================
# My implementation
# (Market-maker, option pricing and delta-hedging)
# ================================================

class MarketMaker(BaseMarketMaker):
    @property
    def name(self) -> str:
        return "Mathieu Chabirand"

    def make_market(self, option: Option) -> tuple[float, float]:
        
        fair_value = self.price_option(option)
        
        # Inputs and parameters (same as in price_option)
        steps_left = int(option.steps_until_expiry)
        
        underlying = None
        for u in self.underlying_state:
            if u.underlying_id == option.underlying_id:
                underlying = u
                break
        
        spot_price = float(underlying.valuation)
        strike_price = float(option.strike)
        up_step = float(underlying.up_move_step)
        down_step = float(underlying.down_move_step)
        probability_up = float(underlying.up_move_probability)
        probability_down = float(underlying.down_move_probability)
        
        # Greeks: estimation of Delta and Gamma repricing the option after bumping the spot (trying to replicate without B&S)
        # Bump size
        bump_size = max(1e-6, 0.5 * (abs(up_step) + abs(down_step)) * 0.5) # 0.2 to 0.5
        
        # Function to price a custom spot (same as price_option) to avoid messing with underlying.valuation
        def price_with_spot(spot_price: float) -> float:
            values = [0.0] * (steps_left + 1)
            for j in range(steps_left + 1):
                final_price = spot_price + (j * up_step) - ((steps_left - j) * down_step)
                if option.option_type.name == "CALL":
                    values[j] = max(final_price - strike_price, 0)
                else: # PUT
                    values[j] = max(strike_price - final_price, 0)
            
            # Backward induction (works backward through the binomial tree)
            for t in range(steps_left - 1, -1, -1):
                for j in range(t + 1):
                    values[j] = (probability_up * values[j + 1]) + (probability_down * values[j])
            return float(values[0])
        
        # Compute bumped prices
        fair_value_up = price_with_spot(spot_price + bump_size)
        fair_value_down = price_with_spot(spot_price - bump_size)
        
        # Delta and Gamma estimates   
        delta_estimate = (fair_value_up - fair_value_down) / (2 * bump_size)
        gamma_estimate = (fair_value_up + fair_value_down - 2 * fair_value) / (bump_size ** 2)
        
        # Spread logic
        jump_scale = abs(up_step) + abs(down_step)
        moneyness = abs(spot_price - float(option.strike)) / max(1, spot_price)
        option_step_scale = max(1e-6, 0.5 * jump_scale)
        price_scale = max(1, fair_value)
        
        base_abs_spread = 0.1 # 0.1 to 0.5
        base_pct_spread = price_scale * 0.006 # 0.006 to 0.015
        base_spread = base_abs_spread + base_pct_spread
        
        jump_coeff = 0.10 # 0.05 to 0.10
        jump_addon = jump_coeff * jump_scale
        
        delta_coeff = 0.15 # 0.10 to 0.20
        gamma_coeff = 0.03 # 0.03 to 0.08
        delta_term = delta_coeff * min(1, abs(delta_estimate))
        gamma_term = gamma_coeff * min(0, abs(gamma_estimate) * option_step_scale)
        risk_spread = delta_term + gamma_term
        
        time_strength = 1.5 # 1.0 to 2.0
        time_factor = 1 + time_strength / (1 + steps_left) # Wider spread close to expiry
        
        is_calm_underlying = jump_scale < 2
        is_far_from_expiry = steps_left >= 3
        is_not_ultra_atm = moneyness >= 0.10
        
        if is_calm_underlying and is_far_from_expiry and is_not_ultra_atm:
            spread = min(spread, 0.80) # To beat 1.0 Fixed Width
        else:
            spread = (base_spread + jump_addon + risk_spread) * time_factor
            
        min_spread = 0.03
        max_spread = 10.0 + 0.10 * price_scale
        spread = max(min_spread, (min(spread, max_spread)))
        half_spread = spread / 2
        
        # At expiry: quote intrisic + tiny
        if steps_left <= 0:
            if option.option_type.name == "CALL":
                intrisic = max(spot_price - strike_price, 0)
            else: # PUT
                intrisic = max(strike_price - spot_price, 0)
            tiny = 0.1
            bid = max(intrinsic - tiny, 0)
            offer = intrinsic + tiny
            return (bid, offer)
        
        # Final bid and offer
        bid = max(fair_value - half_spread, 0)
        offer = fair_value + half_spread
        return (bid, offer)

    def price_option(self, option: Option) -> float:
        
        # Steps until expiry
        steps_left = int(option.steps_until_expiry)
        
        # Find the underlying of the option
        underlying = None
        for u in self.underlying_state:
            if u.underlying_id == option.underlying_id:
                underlying = u
                break
        
        # Define parameters
        spot_price = float(underlying.valuation)
        strike_price = float(option.strike)
        up_step = float(underlying.up_move_step)
        down_step = float(underlying.down_move_step)
        probability_up = float(underlying.up_move_probability)
        probability_down = float(underlying.down_move_probability)
        
        # Options values
        #  - If option expired --> return intrisic value
        if steps_left <= 0:
            if option.option_type.name == "CALL":
                return max(spot_price - strike_price, 0)
            else: # PUT
                return max(strike_price - spot_price, 0)

        #  - Else: Compute payoff values at expiry
        values = [0.0] * (steps_left + 1)
        for j in range(steps_left + 1):
            final_price = spot_price + (j * up_step) - ((steps_left - j) * down_step)
            if option.option_type.name == "CALL":
                values[j] = max(final_price - strike_price, 0)
            else: # PUT
                values[j] = max(strike_price - final_price, 0)
        
        # Backward induction (works backward through the binomial tree)
        for t in range(steps_left - 1, -1, -1):
            for j in range(t + 1):
                values[j] = (probability_up * values[j + 1]) + (probability_down * values[j])

        return float(values[0])
        

    def on_bid_hit(self, option: Option, bid_price: float) -> None:
        super().on_bid_hit(option, bid_price)
        # optional: your code here

    def on_offer_hit(self, option: Option, offer_price: float) -> None:
        super().on_offer_hit(option, offer_price)
        # optional: your code here

    def on_step_advance(self, new_underlying_state: list[Underlying], new_option_state: list[Option]) -> None:
        super().on_step_advance(new_underlying_state, new_option_state)
        
        # Underlyings by id (for quick access)
        underlyings_by_id = {u.underlying_id: u for u in self.underlying_state}
        
        # Net Delta starts with which underlying we currently hold (delta = 1 per unit)
        net_delta_by_underlying = {}
        for underlying_id, quantity in self.position.underlying_quantity_by_underlying_id.items():
            net_delta_by_underlying[underlying_id] = float(quantity)
        
        # Add Delta from each option we hold
        for option in self.active_option_state:
            option_quantity = float(self.position.option_quantity_by_option_id.get(option.option_id, 0))
            if option_quantity == 0:
                continue
            
            underlying = underlyings_by_id[option.underlying_id]
            steps_left = int(option.steps_until_expiry)    
            spot_price = float(underlying.valuation)
            strike_price = float(option.strike)
            up_step = float(underlying.up_move_step)
            down_step = float(underlying.down_move_step)
            probability_up = float(underlying.up_move_probability)
            probability_down = float(underlying.down_move_probability)
            
            # Bump size
            bump_size = max(1e-6, 0.5 * (abs(up_step) + abs(down_step)) * 0.5) # 0.2 to 0.5
            
            # Price with custom spot (same as in make_market)
            def price_with_spot(spot_price: float) -> float:
                values = [0.0] * (steps_left + 1)
                for j in range(steps_left + 1):
                    final_price = spot_price + (j * up_step) - ((steps_left - j) * down_step)
                    if option.option_type.name == "CALL":
                        values[j] = max(final_price - strike_price, 0)
                    else: # PUT
                        values[j] = max(strike_price - final_price, 0)
                
                # Backward induction (works backward through the binomial tree)
                for t in range(steps_left - 1, -1, -1):
                    for j in range(t + 1):
                        values[j] = (probability_up * values[j + 1]) + (probability_down * values[j])
                return float(values[0])
            
            # Bumped prices
            value_up = price_with_spot(spot_price + bump_size)
            value_down = price_with_spot(spot_price - bump_size)
            
            # Delta estimates for the option and contribution to underlying
            delta_estimate = (value_up - value_down) / (2 * bump_size)
            net_delta_by_underlying[option.underlying_id] = (
                net_delta_by_underlying.get(option.underlying_id, 0) + option_quantity * delta_estimate
            )
        
        # Hedge with underlying if Delta outside a safe band
        for underlying_id, delta_total in net_delta_by_underlying.items():
            underlying = underlyings_by_id[underlying_id]
        
            # Define safe band
            safe_band = 0.1 # max(0, 0.5 * (abs(underlying.up_move_step) + abs(underlying.down_move_step)))
            if abs(delta_total) <= safe_band:
                continue # if already within the band
            
            # Soft edge to reduce excess exposure
            target_edge = safe_band if delta_total > 0 else -safe_band
            excess_exposure = delta_total - target_edge
            adjustment = excess_exposure * (-1.00) # Reduce 60% of excess exposure
            quantity_to_trade = int(round(adjustment))
            
            # Trade the underlying
            if quantity_to_trade > 0:
                self.buy_underlying(underlying_id, quantity_to_trade)
            elif quantity_to_trade < 0:
                self.sell_underlying(underlying_id, -quantity_to_trade)
            # If quantity is 0, no need to trade