# Phase 2 client strategy specification

Use the frozen Phase 1 SPY snapshot in USD for 2011–2018 only. Start with $100,000 cash and zero shares. Use provider Close with yfinance automatic adjustment disabled. The provider may already normalize historical prices for splits. Adj Close plays no role in signals, fills, or marks.

## Signals and orders

At each completed trading session close, compute simple averages of the latest 21 and 50 completed daily closes, including that session. Target long when both averages exist and SMA21 is strictly greater than SMA50. Until both exist, and whenever the averages are equal or SMA21 is lower, target cash. An exposure change can fill only at the next available session's provider Open. For example, a target formed after Friday's close can fill at Monday's open if Monday trades. A final target change beyond the development boundary remains unfilled. Mark every session at Close and leave any ending shares open.

Buy once on entry using available cash inclusive of costs. Sell all shares on exit. Long-only with fractional shares, no borrowing, no leverage, and no shorts. Fractional quantities have no broker lot-size rounding. Orders are modeled as immediate full fills at the reported open, including any overnight gap. The 5 basis point charge is 0.0005 times the traded notional on each fill and represents illustrative combined trading friction. No separate commissions, bid-ask spread, slippage, market impact, taxes, settlement delay, or idle cash interest is modeled.

## Distributions and accounting

At the start of each session, credit the previous close's share count times each per-share amount in Dividends and Capital Gains on its provider event date. This treats the date as ex-date and proxies actual payment with immediate cash. Shares purchased at that open receive no credit. Shares sold at that open retain the credit. A position held through the ex-date keeps proceeds in cash until a subsequent entry. Adjusted prices would embed distributions and would double count them if used alongside cash credits. Reject nonzero split events because split-adjusted vendor bars and share-count changes need an explicit common basis. Other unsupported corporate actions require separate data and accounting.

Keep full model precision and allow only floating-point roundoff in reconciliations. Daily cash equals prior cash plus distributions and net fill cash flow. Shares equal prior shares plus signed fill shares. Closing equity equals cash plus shares times Close. Independently bridge equity via distribution income, prior shares' overnight price move, post-fill shares' open-to-close move, and trading charges.

## Weekly and monthly regimes

A weekly bar uses the close of the last scheduled exchange session in a Monday–Sunday calendar week. A monthly bar uses the close of the last scheduled exchange session in the calendar month. Use the exchange calendar to identify these boundaries, including holiday-shortened weeks and months. An incomplete period at a dataset boundary supplies no period-close observation. A completed period's label can first be known after that session closes and can be consumed at the next session open. Any future label series would use only completed bars and stay independent of daily orders. The research specification gives daily lookbacks and leaves weekly and monthly lookbacks open, so Phase 2 produces daily signals only.
