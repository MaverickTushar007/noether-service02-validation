"""Render the Phase 4 evidence from computed rows."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter


def write_figures(output, bounds, cases):
    fig, ax = plt.subplots(figsize=(8, 3.4), layout="constrained")
    for i, row in enumerate(bounds):
        point = row["annualized_mean"]
        ax.errorbar(point, i, xerr=[[point-row["annualized_lower"]], [row["annualized_upper"]-point]],
                    fmt="o", color="#144e66" if row["primary"] else "#5b7180", capsize=5)
    ax.axvline(0, color="#888888", linestyle="--", linewidth=1)
    ax.set_yticks(range(len(bounds)), [f'{r["block_sessions"]} sessions' + (" (primary)" if r["primary"] else "")
                                       for r in bounds])
    ax.invert_yaxis()
    ax.xaxis.set_major_formatter(PercentFormatter(1))
    ax.set_xlabel("Annualized arithmetic mean")
    ax.set_title("Development return and 95% moving-block intervals", loc="left")
    fig.savefig(output / "bootstrap_intervals.png", dpi=150)
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(8, 3.7), layout="constrained", sharey=True)
    parameter = [r for r in cases if r["cost_bps_per_fill"] == 5]
    costs = [r for r in cases if (r["fast"], r["slow"]) == (21, 50)]
    for ax, data, labels, title in [
        (axes[0], parameter, [f'{r["fast"]}/{r["slow"]}' for r in parameter], "SMA lookbacks · 5 bp"),
        (axes[1], costs, [f'{r["cost_bps_per_fill"]} bp' for r in costs], "Per-fill fees · SMA 21/50"),
    ]:
        ax.bar(labels, [r["cagr"] for r in data], color="#35718a", width=0.55)
        ax.axhline(0, color="#888888", linewidth=1)
        ax.set_title(title, loc="left")
        ax.grid(axis="y", alpha=0.2)
    axes[0].yaxis.set_major_formatter(PercentFormatter(1))
    axes[0].set_ylabel("Development CAGR")
    fig.savefig(output / "diagnostic_cagr.png", dpi=150)
    plt.close(fig)


def write_report(output, dates, stats, bounds, cases, regimes, findings):
    primary = bounds[0]
    lines = [
        "# Phase 4 statistical robustness and bias review", "",
        f"The analysis covers {len(dates):,} development sessions from {dates[0]} through {dates[-1]}. The frozen "
        "rule starts with $100,000, earns zero interest on idle cash and applies 5 bp per fill in the reference "
        "case. This is development-period evidence for a hypothetical strategy.", "",
        "## Return uncertainty", "",
        f"The mean net daily return was {primary['mean_daily']:.5%}. The annualized arithmetic mean was "
        f"{primary['annualized_mean']:.2%} and the geometric CAGR was {stats['cagr']:.2%}. Annualized arithmetic "
        "mean multiplies the daily mean by 252. CAGR takes the geometric growth of the ending balance.", "",
        f"Closing shares were positive on {stats['long_closes']:,} sessions ({stats['fraction_long_closes']:.2%}). "
        f"Mean closing invested weight was {stats['mean_close_invested_weight']:.2%}. Annualized gross "
        f"turnover was {stats['annualized_gross_turnover']:.2%} of prior equity ({stats['gross_turnover']:.2f}× "
        "across development). Buys and sells each enter gross turnover at full notional.", "",
        "The tested null is zero mean net daily return. Two-sided inference uses the 95% percentile interval. "
        "Non-circular blocks were sampled with replacement from simple daily returns, with 20,000 replications "
        "per length and PCG64 seed 20261127. The primary choice is 20 sessions.", "",
        "| Block | Daily 95% interval | Annualized arithmetic 95% interval | Zero excluded |",
        "| --- | ---: | ---: | --- |",
    ]
    for row in bounds:
        lines.append(f"| {row['block_sessions']} | [{row['daily_lower']:.5%}, {row['daily_upper']:.5%}] | "
                     f"[{row['annualized_lower']:.2%}, {row['annualized_upper']:.2%}] | "
                     f"{'Yes' if row['zero_excluded'] else 'No'} |")
    lines.extend(["", "An interval including zero leaves the mean unresolved under the protocol. It supplies no "
                  "proof that a predictive effect is absent. The intervals rely on approximate stationarity "
                  "and sufficient dependence coverage within blocks. They are conditional on the chosen rule "
                  "and development window and do not adjust for historical selection.", "",
                  "![Moving-block intervals](bootstrap_intervals.png)", "",
                  "## Prespecified diagnostic runs", "",
                  "Each case recomputes costs, shares, cash and equity. Two implementations agree on the "
                  "dates, decisions, fills, distributions and daily equity. Parameter cases are exploratory. "
                  "The cost grid illustrates model sensitivity to fees and uses no verified historical fill costs.", "",
                  "| SMA | Fee per fill | Fills | Cost | Total return | CAGR | Max drawdown |",
                  "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"])
    for row in cases:
        lines.append(f"| {row['fast']}/{row['slow']} | {row['cost_bps_per_fill']} bp | {row['fills']} | "
                     f"${row['total_cost_usd']:,.2f} | {row['total_return']:.2%} | {row['cagr']:.2%} | "
                     f"{row['max_drawdown']:.2%} |")
    lines.extend(["", "![Sensitivity diagnostic CAGR](diagnostic_cagr.png)", "",
                  "## Signal timing and descriptive labels", "",
                  "Close-based signals are available after the final close of the corresponding period. "
                  "Trade and regime consumption is eligible at the following scheduled open. The weekly "
                  "definition uses Monday–Sunday weeks and the monthly definition uses calendar months. "
                  "An incomplete week at the sample end supplies no period observation. Weekly and monthly "
                  "labels are descriptive and place no orders.", "",
                  "| Frequency | Completed bars | Warmup | Ready | Long | Cash | Enter | Exit | First ready |",
                  "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |"])
    for row in regimes:
        lines.append(f"| {row['frequency']} | {row['completed_bars']} | {row['warmup_bars']} | {row['ready_labels']} | "
                     f"{row['long_labels']} | {row['cash_labels']} | {row['enter_transitions']} | "
                     f"{row['exit_transitions']} | {row['first_ready_close']} |")
    lines.extend(["", "Monthly counts have few transitions and no regime-conditioned inference is made. "
                  "The code and saved ledgers pass the timing checks. Controlled early fills and early label "
                  "releases are challenged in tests, separately from the observed SPY findings. The data "
                  "do not measure vendor publication latency or historical execution feasibility.", "",
                  "## Findings", "", "| ID | Status | Criterion | Evidence |", "| --- | --- | --- | --- |"])
    lines += [f"| {a} | {b} | {c} | {d} |" for a, b, c, d in findings]
    lines.extend(["", "No independent selection history is available for the asset, sample dates, or moving averages. "
                  "The statistical screen is conditional on this selected development sample. Long SPY exposure "
                  "can contribute to returns, so incremental value remains unresolved without a prespecified "
                  "benchmark or risk comparison. Ex-date cash timing retains the Phase 3 limitation.", "",
                  "See the [protocol](../../reports/statistical-protocol.md) for the hypotheses, fixed settings "
                  "and criterion definitions."])
    (output / "statistical-review.md").write_text("\n".join(lines) + "\n")
