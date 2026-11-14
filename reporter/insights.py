"""Turn the KPI tables into plain-English findings, recommendations and slide titles."""
from dataclasses import dataclass, field

from .formatting import money, pct


@dataclass
class Insights:
    findings: list = field(default_factory=list)
    recommendations: list = field(default_factory=list)
    titles: dict = field(default_factory=dict)


def plural(n, word):
    return f"{n:,} {word}" + ("" if n == 1 else "s")


def compare_groups(table, label_col):
    """Best and worst group by ROAS, and the gap between them."""
    ranked = table.sort_values("roas", ascending=False)
    best, worst = ranked.iloc[0], ranked.iloc[-1]
    gap = best["roas"] / worst["roas"] - 1
    return best[label_col], best["roas"], worst[label_col], worst["roas"], gap


def group_finding(table, label_col, noun, cfg):
    cur = cfg["currency"]
    best, best_roas, worst, worst_roas, gap = compare_groups(table, label_col)
    if gap < cfg["thresholds"]["similar_gap"]:
        return (
            f"{best} is the best {noun} for return on spend ({cur}{best_roas:.2f} back per {cur}1), "
            f"but {noun}s are close: the weakest, {worst}, is only {pct(gap)} behind at {cur}{worst_roas:.2f}."
        )
    return (
        f"{best} gives the best return on spend of any {noun} ({cur}{best_roas:.2f} per {cur}1), "
        f"{pct(gap, 0)} ahead of {worst} ({cur}{worst_roas:.2f})."
    )


def generate_insights(data, cfg) -> Insights:
    cur = cfg["currency"]
    similar = cfg["thresholds"]["similar_gap"]
    week_change = cfg["thresholds"]["week_change"]
    out = Insights()
    o = data.overall
    c = data.campaigns

    # 1-2. channel and segment: the main storyline
    ch_best, _, ch_worst, _, ch_gap = compare_groups(data.by_channel, "channel")
    out.findings.append(group_finding(data.by_channel, "channel", "channel", cfg))
    seg_best, seg_gap = None, None
    if data.by_segment is not None:
        seg_best, _, _, _, seg_gap = compare_groups(data.by_segment, "segment")
        out.findings.append(group_finding(data.by_segment, "segment", "segment", cfg))

    # 3. loss-making campaigns
    losers = c[c["roi"] < 0]
    loss_share = len(losers) / len(c)
    loss_spend_share = losers["spend"].sum() / c["spend"].sum()
    out.findings.append(
        f"{pct(loss_share, 0)} of campaigns ({len(losers):,}) lost money: they used "
        f"{pct(loss_spend_share, 0)} of total spend ({money(losers['spend'].sum(), cur)}) "
        f"and brought back {money(losers['revenue'].sum(), cur)}."
    )

    # 4. outliers
    if len(data.outliers):
        top = data.outliers.sort_values("roi", ascending=False).iloc[0]
        out.findings.append(
            f"{len(data.outliers):,} campaigns sit far from their channel's average. The strongest, "
            f"{top['campaign']} ({top['channel']}), returned {cur}{top['roas']:.0f} per {cur}1 "
            f"at a cost per conversion of {cur}{top['cost_per_conversion']:.0f}."
        )

    # 5. weekly anomalies, or duration if there are no dates
    flagged = data.weekly[data.weekly["anomaly"]] if data.weekly is not None else None
    volume_driven = False
    if flagged is not None:
        if len(flagged):
            worst_week = flagged.loc[flagged["revenue_change"].abs().idxmax()]
            # did the number of campaigns move as much as the result did?
            volume_driven = bool((flagged["campaigns_change"].abs() > week_change).all())
            out.findings.append(
                f"{plural(len(flagged), 'week')} moved more than {pct(week_change, 0)} week-on-week. The largest was "
                f"a {worst_week['revenue_change']:+.0%} change in revenue in the week of "
                f"{worst_week['week']:%d %b %Y}, when {worst_week['campaigns']:,} campaigns ran "
                f"({worst_week['campaigns_change']:+.0%} vs the week before)."
            )
        else:
            out.findings.append(
                f"Performance was steady: no full week moved more than {pct(week_change, 0)} week-on-week."
            )
    if data.by_duration is not None and len(out.findings) < 6:
        band_best, band_best_roas, band_worst, band_worst_roas, _ = compare_groups(data.by_duration, "duration_band")
        out.findings.append(
            f"Campaigns lasting {band_best} return the most ({cur}{band_best_roas:.2f} per {cur}1); "
            f"those lasting {band_worst} return the least ({cur}{band_worst_roas:.2f})."
        )

    # recommendations
    out.recommendations.append(
        f"Review the {len(losers):,} loss-making campaigns first: together they spent "
        f"{money(losers['spend'].sum() - losers['revenue'].sum(), cur)} more than they earned back."
    )
    target = ch_best + (f" and the {seg_best} segment" if seg_best else "")
    if ch_gap < similar:
        out.recommendations.append(
            f"Don't move large budgets between channels on a {pct(ch_gap)} gap. Test it: shift around 10% of "
            f"budget toward {target} for a few weeks and compare against a control."
        )
    else:
        out.recommendations.append(f"Shift budget toward {target}, then track whether the return holds.")
    if len(data.outliers):
        out.recommendations.append(
            "Study the top outlier campaigns (targeting, creative, cost per conversion) and reuse what works."
        )
    out.recommendations.append(
        f"Run this report every week so swings over {pct(week_change, 0)} are spotted within days."
    )

    # slide titles state the finding
    t = out.titles
    t["kpi"] = (
        f"{money(o['revenue'], cur)} revenue from {money(o['spend'], cur)} spend: "
        f"every {cur}1 returned {cur}{o['roas']:.2f}"
    )
    t["channel"] = (
        f"{ch_best} leads on return, but all channels sit within {pct(ch_gap)}"
        if ch_gap < similar else f"{ch_best} delivers the highest return on spend"
    )
    if seg_best:
        t["segment"] = (
            f"{seg_best} is the strongest segment, by a narrow {pct(seg_gap)}"
            if seg_gap < similar else f"{seg_best} gives the best return on spend"
        )
    t["campaigns"] = (
        f"{pct(loss_share, 0)} of campaigns lost money, while the best returned "
        f"{cur}{c['roas'].max():.0f} per {cur}1"
    )
    if flagged is not None:
        if not len(flagged):
            t["weekly"] = "Weekly performance held steady across the period"
        elif volume_driven:
            t["weekly"] = (
                f"{plural(len(flagged), 'week')} swung more than {pct(week_change, 0)}, "
                "driven by how many campaigns ran"
            )
        else:
            t["weekly"] = f"{plural(len(flagged), 'week')} swung more than {pct(week_change, 0)}: worth a closer look"
    t["findings"] = (
        "The bigger gains are inside channels, not between them"
        if ch_gap < similar else f"{ch_best} and strong campaigns drive the return"
    )
    t["recommendations"] = (
        "Fix loss-making campaigns first, then test budget shifts"
        if loss_share > 0.1 else f"Shift budget toward {ch_best} and keep testing"
    )

    out.findings = out.findings[:6]
    return out
