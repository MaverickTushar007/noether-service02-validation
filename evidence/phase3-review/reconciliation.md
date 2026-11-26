# Phase 3 mathematical reconciliation

SPY development sessions only, 2011–2018. The reviewer parsed the frozen analysis CSV and independently summed complete 21- and 50-close windows using 40-digit decimal arithmetic. The sign of the SMA difference uses cross-multiplied window sums. The portfolio uses the prior session's target at each open. On buys, gross notional equals available cash divided by 1.0005. On sales, gross proceeds less 5 bp and any already available cash determine the new balance. A close mark equals cash plus shares times Close.

Reproduced 2012 sessions and 44 fills. Ending equity was $151,462.65. Maximum reviewer cash, share, and equity-bridge residuals were 0.000E+2, 0.000E+3, and 1.000E-34, respectively.

## Metric conventions

Daily simple returns use closing equity over the preceding close, with $100,000 as the starting observation before the first session. Total return is final equity divided by $100,000 minus one. Geometric annualized return raises that same equity ratio to 252 divided by the number of daily returns, then subtracts one. Volatility is sample daily standard deviation (ddof=1) times the square root of 252. Sharpe uses the arithmetic mean of daily returns over sample daily standard deviation, times the square root of 252, with a zero risk-free rate. Idle cash earns zero interest. Drawdown is the largest positive decline from the running equity peak, including starting capital, divided by that peak. For example, equity of 100, 120, 90, 110 has a 25% maximum drawdown.

Phase 2 submitted no performance metrics. The client column below was calculated from its saved equity using separate floating-point formulas and the same conventions.

| Metric | Reviewer | Derived from client equity |
| --- | ---: | ---: |
| total return | 51.46264623% | 51.46264623% |
| annualized return | 5.33749833% | 5.33749833% |
| annualized volatility | 10.18849321% | 10.18849321% |
| annualized sharpe | 0.56158920 | 0.56158920 |
| max drawdown | 25.59734130% | 25.59734130% |

## Comparison and findings

Dates, labels, warmup blanks, and row order were compared exactly. Numerical comparisons used absolute tolerance plus 1e-12 times the absolute client value. Absolute tolerances were 1e-10 USD for market prices and SMA, 1e-9 shares for quantities, 1e-8 USD for cash and accounting, and 1e-12 for decimal metrics. Relative error is absolute error divided by absolute client value. Zero client values are included in absolute error only. Near-zero client residuals can give large relative errors even when absolute differences are at roundoff scale.

The [comparison CSV](comparison.csv) records maximum absolute and relative differences, counts, and the first mismatching key per field. The [findings register](findings.csv) covers actual submission results. Intentionally altered scenarios are exercised separately by the reviewer tests.

| ID | Status | Finding |
| --- | --- | --- |
| F01 | PASS | Frozen inputs and client output/source integrity. SHA-256 matches the recorded references. |
| F02 | PASS | Client settings versus written scope. Compared Phase 2 parameters with the reviewer transcription. |
| F03 | PASS | Development session coverage. All 2012 expected XNYS sessions matched. |
| F04 | PASS | SMA, warmup, targets and crossover dates. All fields matched within tolerance. |
| F05 | PASS | Signal-to-fill dates, opening executions and fees. All fields matched within tolerance. |
| F06 | PASS | Daily shares, cash, distributions and equity. All fields matched within tolerance. |
| F07 | PASS | Submitted accounting totals. All fields matched within tolerance. |
| F08 | PASS | Metrics recalculated from client equity. All fields matched within tolerance. |
| F09 | INCONCLUSIVE | Client-submitted performance metric values. Phase 2 submitted equity but no performance metrics. F08 compares recalculations. |
| F10 | INCONCLUSIVE | Impact of ex-date cash availability. Payment dates and settlement cash were not modeled or tested. |
| F11 | PASS | Reviewer cash, shares and equity reconciliation. Checked ending-of-session balances and daily accounting identities. |

| Field | Maximum absolute difference | Maximum relative difference |
| --- | ---: | ---: |
| signals sma_fast | 5.000E-14 | 1.911E-16 |
| signals sma_slow | 5.100E-14 | 1.922E-16 |
| fills shares_delta | 8.521E-13 | 1.591E-15 |
| fills cost | 1.306E-13 | 1.739E-15 |
| daily dividend_cash | 1.093E-12 | 1.638E-15 |
| daily cash | 2.350E-10 | 1.638E-15 |
| daily equity | 2.900E-10 | 1.854E-15 |

## Distributions and settlement

The reviewer reproduced cash credits on 24 entitled sessions, including 0 sessions with an opening sale. Prior-close holdings receive the distribution. Opening buyers receive none for that date. Credits use the provider event date as an ex-date proxy. Economic entitlement can arise at the ex date while spendable cash depends on the payment date and the broker's availability rules. The model makes these credits spendable immediately, potentially earlier than real cash availability if a later entry falls before payment. The model carries cash during a long holding period and sizes a subsequent entry with available cash. Payment-date data and a counterfactual ledger were outside this reconciliation, so no performance effect was established.
