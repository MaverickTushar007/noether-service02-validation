"""Render Phase 5 artifacts from the single in-memory evaluation."""
from datetime import date

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.dates import DateFormatter, YearLocator
from matplotlib.ticker import PercentFormatter

from .metrics import drawdowns

LABELS = {"sma": "SMA 21/50", "buy_hold": "SPY buy and hold",
          "cash": "Treasury cash proxy", "fixed_mix": "Fixed SPY/cash mix"}
COLORS = {"sma": "#164e66", "buy_hold": "#a65032", "cash": "#52665f", "fixed_mix": "#77609a"}


def render_charts(output, books):
    for metric, title, filename in (
        ("equity", "Portfolio growth from $100,000", "equity.png"),
        ("drawdown", "Decline from running peak", "drawdown.png"),
    ):
        fig, axes = plt.subplots(1, 2, figsize=(11, 4), sharey=True, layout="constrained")
        for ax, (period, items) in zip(axes, books.items(), strict=True):
            for book, ledger in items.items():
                x = [date.fromisoformat(row["date"]) for row in ledger]
                values = [float(row["equity"]) for row in ledger]
                y = values if metric == "equity" else drawdowns(values)
                ax.plot(x, y, label=LABELS[book], color=COLORS[book], linewidth=1.2)
            ax.xaxis.set_major_locator(YearLocator())
            ax.xaxis.set_major_formatter(DateFormatter("%Y"))
            ax.set_title(period.capitalize())
            ax.grid(alpha=0.25)
        if metric == "drawdown":
            axes[0].yaxis.set_major_formatter(PercentFormatter(1))
            axes[0].invert_yaxis()
        else:
            axes[0].set_ylabel("USD")
        axes[0].legend(loc="best", fontsize=8)
        fig.suptitle(title)
        fig.savefig(output / filename, dpi=150)
        plt.close(fig)

def render(output, books, comparison, uncertainty, checks, findings, windows, same):
    render_charts(output, books)
    holdout = books["holdout"]["sma"]
    first = holdout[0]
    primary = next(row for row in uncertainty if row["window"] == "holdout" and row["benchmark"] == "fixed_mix")
    lines = [
        "# Phase 5 benchmark and out-of-sample review", "",
        "This is a one-shot evaluation of a hypothetical strategy under the frozen protocol. "
        "Each window starts with $100,000 and zero shares. The holdout initial target uses the final "
        "50 development closes. All four books share matched sessions, a provider price basis, and "
        "common per-share distributions and trading fees on SPY fills.", "",
        f"On {first['date']}, the carried-forward SMA target from {first['signal_date']} was "
        f"{'long' if first['open_target_long'] else 'cash'}. The first open "
        f"{'had a modeled ' + first['trade_reason'] if first['trade_reason'] else 'required no SMA fill'}. "
        "The first session included no carryover cash interest, inventory or distribution entitlement.", "",
        "## Performance", "",
        "| Window | Portfolio | Sessions | Cumulative | CAGR | Volatility | Excess Sharpe | Max drawdown | Underwater sessions | Mean SPY weight | Cost |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in comparison:
        sharpe = f"{row['excess_sharpe']:.3f}" if row["excess_sharpe"] != "" else "Undefined"
        lines.append(f"| {row['window']} | {LABELS[row['portfolio']]} | {row['sessions']} | "
                     f"{row['cumulative_return']:.2%} | {row['cagr']:.2%} | {row['annualized_volatility']:.2%} | "
                     f"{sharpe} | {row['maximum_drawdown']:.2%} | {row['longest_underwater_sessions']} | "
                     f"{row['mean_invested_weight']:.2%} | ${row['modeled_cost_usd']:,.2f} |")
    lines.extend([
        "", "CAGR uses 252 trading sessions per year. Sharpe uses daily excess returns over the common "
        "DTB3 accrual proxy. The cash book has undefined Sharpe because its theoretical excess return is "
        "zero each day. Drawdown duration is the longest consecutive run below an equity peak, including "
        "open drawdowns at the sample end. Gross turnover and dollar distributions are in the comparison CSV.", "",
        "![Equity by evaluation window](equity.png)", "",
        "![Drawdowns by evaluation window](drawdown.png)", "",
        "## Paired return differences", "",
        "Differences are SMA minus benchmark. The compounded gap subtracts cumulative portfolio returns. "
        "The uncertainty column is the 95% interval for the paired arithmetic mean times 252.", "",
        "| Window | Benchmark | Compounded gap | Annualized arithmetic gap | 95% interval |",
        "| --- | --- | ---: | ---: | ---: |",
    ])
    for row in uncertainty:
        lines.append(f"| {row['window']} | {LABELS[row['benchmark']]} | {row['compounded_total_return_gap']:.2%} | "
                     f"{row['annualized_arithmetic_gap']:.2%} | "
                     f"[{row['annualized_ci_lower']:.2%}, {row['annualized_ci_upper']:.2%}] |")
    lines.extend([
        "", f"The primary compounded gap was {primary['compounded_total_return_gap']:.2%}. The primary result "
        "uses the prespecified joint interval and compounded-gap criterion. Secondary and development "
        "intervals are descriptive. The intervals retain within-block dependence and are conditional on "
        "this sample and the block design.", "",
        "## Prespecified context windows", "",
        "| Window | Portfolio | Actual dates | Sessions | Cumulative return |",
        "| --- | --- | --- | ---: | ---: |",
    ])
    for row in windows:
        lines.append(f"| {row['window']} | {LABELS[row['portfolio']]} | {row['start']} to {row['end']} | "
                     f"{row['sessions']} | {row['cumulative_return']:.2%} |")
    lines.extend([
        "", "Window returns use the preceding close or the initial cash balance. They describe behavior "
        "in named historical periods. The benchmarks differ in realized exposure and exposure timing. "
        "A drawdown or return gap cannot isolate the timing effect from exposure, cash yield and fee drag.", "",
        "## Reviewer reconciliation and limitations", "",
        f"The development strategy matched the Phase 3 frozen reviewer path to {same:.3E}. The largest "
        f"ledger identity residual across both windows was "
        f"{max(float(row['maximum_identity_residual']) for row in checks):.3E}. "
        "The independent checks validate prior-close entitlement, cash accrual, the next eligible open, "
        "common fill costs, exact post-fee opening target weight, and daily share/cash/mark identities.", "",
        "Historical DTB3 rates are verified. They support a synthetic lagged cash accrual using a 91-day "
        "bill-price conversion. The cash proxy does not replicate executable bill total returns or broker "
        "cash yields. The source vintage was retrieved after the evaluation periods. Using ex-date credits "
        "can advance spendability relative to settlement. The original SMA retains zero idle cash interest. "
        "Buy and hold reinvests from the following session open. These assumptions can affect relative performance.", "",
        "| ID | Status | Criterion | Evidence |", "| --- | --- | --- | --- |",
    ])
    lines.extend(f"| {row['id']} | {row['status']} | {row['criterion']} | {row['evidence']} |" for row in findings)
    lines.extend(["", "See the [frozen protocol](../../reports/evaluation-protocol.md) for rules and decision thresholds. "
                  "Phase 3 and Phase 4 conclusions remain in their original evidence."])
    (output / "evaluation.md").write_text("\n".join(lines) + "\n")
