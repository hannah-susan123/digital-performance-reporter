"""PNG charts for the slides and for use on a website."""
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # no window needed
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import StrMethodFormatter  # noqa: E402

from .formatting import BLUE, GREY, INK, INK_SOFT, RED, SURFACE  # noqa: E402


def _c(hex_code):
    return "#" + hex_code


plt.rcParams.update({
    "font.family": ["Segoe UI", "DejaVu Sans"],  # Segoe UI on Windows, fallback elsewhere
    "font.size": 12,
    "axes.edgecolor": _c(GREY),
    "axes.labelcolor": _c(INK_SOFT),
    "xtick.color": _c(INK_SOFT),
    "ytick.color": _c(INK),
    "figure.facecolor": _c(SURFACE),
    "axes.facecolor": _c(SURFACE),
})


def _new_figure(title, subtitle):
    fig, ax = plt.subplots(figsize=(10, 5.6), dpi=200)
    fig.text(0.02, 0.95, title, fontsize=17, fontweight="bold", color=_c(INK), va="top")
    fig.text(0.02, 0.885, subtitle, fontsize=11.5, color=_c(INK_SOFT), va="top")
    for side in ["top", "right"]:
        ax.spines[side].set_visible(False)
    return fig, ax


def _save(fig, path):
    fig.subplots_adjust(top=0.8)
    fig.savefig(path, facecolor=fig.get_facecolor())
    plt.close(fig)
    return path


def roas_bar(table, label_col, noun, overall_roas, path, cur="₹"):
    """Horizontal bars, best group in blue, the rest grey, from a zero baseline."""
    t = table.sort_values("roas")  # best ends up at the top
    colours = [_c(GREY)] * len(t)
    colours[-1] = _c(BLUE)
    fig, ax = _new_figure(
        f"Return on ad spend by {noun}",
        f"Revenue per {cur}1 spent. Dashed line = overall average ({cur}{overall_roas:.2f})",
    )
    bars = ax.barh(t[label_col].astype(str), t["roas"], color=colours, height=0.62)
    for bar, value in zip(bars, t["roas"]):
        # start the label past the average line so they never overlap
        ax.text(max(bar.get_width(), overall_roas) + 0.05, bar.get_y() + bar.get_height() / 2,
                f"{cur}{value:.2f}", va="center", fontsize=12, color=_c(INK))
    ax.axvline(overall_roas, color=_c(INK_SOFT), linestyle="--", linewidth=1.2)
    ax.set_xlim(0, t["roas"].max() * 1.15)
    ax.tick_params(axis="y", length=0)
    ax.spines["left"].set_visible(False)
    ax.set_xlabel(f"ROAS ({cur} revenue per {cur}1 spend)")
    return _save(fig, path)


def weekly_revenue(weekly, path, cur="₹"):
    w = weekly
    full, partial, flagged = w[~w["partial"]], w[w["partial"]], w[w["anomaly"]]
    fig, ax = _new_figure(
        "Weekly revenue",
        f"{cur} crore per week. Red = moved more than the alert threshold vs the previous week",
    )
    ax.plot(w["week"], w["revenue"] / 1e7, color=_c(GREY), linewidth=1.5, linestyle=":")
    ax.plot(full["week"], full["revenue"] / 1e7, color=_c(BLUE), linewidth=2, label="Revenue")
    ax.scatter(partial["week"], partial["revenue"] / 1e7, s=60, facecolors=_c(SURFACE),
               edgecolors=_c(GREY), linewidths=1.5, zorder=3, label="Partial week (not flagged)")
    ax.scatter(flagged["week"], flagged["revenue"] / 1e7, s=90, color=_c(RED),
               edgecolors=_c(SURFACE), linewidths=2, zorder=4, label="Anomaly")
    for _, row in flagged.iterrows():
        ax.annotate(f"{row['revenue_change']:+.0%}", (row["week"], row["revenue"] / 1e7),
                    xytext=(8, -16), textcoords="offset points", fontsize=11, color=_c(INK))
    ax.set_ylim(bottom=0)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.set_ylabel(f"Revenue ({cur} Cr)")
    ax.grid(axis="y", color="#E6E5E0", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, loc="lower left", fontsize=10.5)
    return _save(fig, path)


def campaign_spread(campaigns, path, cur="₹", floor=None):
    """Histogram of campaign ROAS; loss-making campaigns (ROAS < 1) in red."""
    values = campaigns["roas"].dropna()
    cap = math.ceil(values.quantile(0.99))
    clipped = values.clip(upper=cap)
    loss_share = (values < 1).mean()
    fig, ax = _new_figure(
        "How return varies across individual campaigns",
        f"Campaigns by ROAS. {loss_share:.0%} returned less than {cur}1 per {cur}1 spent "
        f"(top 1% grouped at {cur}{cap:.0f})",
    )
    bins = [i * 0.5 for i in range(int(cap / 0.5) + 1)]  # edges land on 1.0 (break-even)
    _, edges, patches = ax.hist(clipped, bins=bins, color=_c(BLUE), edgecolor=_c(SURFACE), linewidth=1)
    for patch, left in zip(patches, edges[:-1]):
        if left < 1:
            patch.set_facecolor(_c(RED))
    ax.axvline(1, color=_c(INK), linewidth=1.2)
    ax.text(1.15, ax.get_ylim()[1] * 0.92, "Break-even", fontsize=11, color=_c(INK))
    if floor:
        # campaigns left of this line are the action list
        top = ax.get_ylim()[1]
        ax.axvline(floor, color=_c(INK), linewidth=1.2, linestyle="--")
        ax.annotate(f"Outlier floor ~{cur}{floor:.2f}: campaigns left\nof the dashed line are the action list",
                    xy=(floor, top * 0.7), xytext=(6, top * 0.7), fontsize=11, color=_c(INK), va="center",
                    arrowprops={"arrowstyle": "->", "color": _c(INK_SOFT)})
    ax.set_xlabel(f"ROAS ({cur} revenue per {cur}1 spend)")
    ax.set_ylabel("Campaigns")
    ax.yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
    ax.grid(axis="y", color="#E6E5E0", linewidth=0.8)
    ax.set_axisbelow(True)
    return _save(fig, path)


def make_charts(data, out_dir, cfg):
    """Draw every chart the data supports; returns {name: path}."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cur = cfg["currency"]
    avg = data.overall["roas"]
    paths = {
        "channel": roas_bar(data.by_channel, "channel", "channel", avg, out_dir / "roas_by_channel.png", cur),
        "campaigns": campaign_spread(
            data.campaigns, out_dir / "campaign_roas_spread.png", cur,
            floor=data.action_list["roas_lower_limit"].median() if len(data.action_list) else None,
        ),
    }
    if data.by_segment is not None:
        paths["segment"] = roas_bar(data.by_segment, "segment", "customer segment", avg,
                                    out_dir / "roas_by_segment.png", cur)
    if data.by_duration is not None:
        paths["duration"] = roas_bar(data.by_duration, "duration_band", "campaign length", avg,
                                     out_dir / "roas_by_duration.png", cur)
    if data.by_platform is not None:
        paths["platform"] = roas_bar(data.by_platform, "platform", "platform", avg,
                                     out_dir / "roas_by_platform.png", cur)
    if data.weekly is not None:
        paths["weekly"] = weekly_revenue(data.weekly, out_dir / "weekly_revenue.png", cur)
    return paths
