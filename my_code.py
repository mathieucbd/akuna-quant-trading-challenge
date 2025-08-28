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