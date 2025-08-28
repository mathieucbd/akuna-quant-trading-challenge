# akuna-quant-trading-challenge
Implementation of Akuna Capital's 2025 Quant Trading Challenge - algorithmic market making and PnL optimization in a simulated options market environment.

This repository contains my submission for the Akuna Quant Trading Challenge.
The challenge simulated a simplified options market where the objective was to design a market making algorithm that maximizes profits while avoiding bankruptcy.

---

**Challenge Structure***
**1. Binomial Option Pricing**
- Implemented a binomial tree to compute theoretical values for European options.
- Used as the baseline for assessing mispricing and guiding quotes.

**2. Market Making Algorithm**
- Main part of the project: design and implement a quoting strategy.
- My approach was focused on:
  -> Volatility and time to maturity
  -> Simulated Delta and Gamma exposures
  -> Adaptive bid/ask spread that reacts to changing market conditions
- Goal: dynamic, adaptive spreads suited to most situations, balancing competitiveness and risk.

**3. Risk Management**
- Integrated a delta-hedging module to manage directional exposure.
- Combined with spread adaptation to mitigate extreme outcomes.

---

**Notes**
- The inputs were proprietary and randomized by Akuna.
- This code is provided for illustrative purposes only; it cannot be run outside of the Akuna environment.
- The focus is on demonstrating the thought process, implementation style, and risk-aware trading logic.
