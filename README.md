# NAVIER — Fluid Dynamics Meets Market Microstructure

**Status: Experimental research · Predictive edge not established**

NAVIER investigates whether mathematical features inspired by fluid dynamics can provide incremental predictive information about cryptocurrency market microstructure, beginning with BTC/USDT Level 2 order-book data.

## Research question

Do fluid-dynamics-inspired features improve out-of-sample predictions beyond conventional market microstructure baselines, including order-book imbalance (OBI) and order-flow imbalance (OFI)?

## Methodology

The project emphasizes:

- Real Level 2 order-book data and data-integrity validation.
- Explicit mathematical definitions and falsifiable hypotheses.
- Reproducible experiments using Python and conventional scientific libraries.
- Chronological out-of-sample evaluation and protection against look-ahead bias.
- Comparisons against conventional baselines.
- Statistical uncertainty and multiple-testing controls.

## Current status

Initial real-data collection and software validation have been performed. Existing mult-session predictive evaluations use BTC/USD, while the BTC/USDT dataset currently available is limited and does not establish predictive performance.

The existing V3 evaluation did not demonstrate a statistically convincing incremental predictive improvement. Its results are retrospective diagnostics, not a new confirmatory test.

No net trading profitability has been established.

## Next milestone

Run a separately versioned, preregistered confirmatory experiment on BTC/USDT, subject to data-quality and sample-size requirements.

## Research principles

- Negative and inconclusive results are reported honestly.
- Synthetic-data validation is not treated as evidence of real-market predictability.
- Predictive improvement is distinguished from economic profitability.
- Existing experimental artifacts are preserved.
- New experiments must have explicit acceptance and stopping criteria.

**This repository is a research project, not a validated trading strategy or investment recommendation.**
