"""Excel workbook: summary, breakdowns, native charts and conditional formatting."""
from datetime import date

import numpy as np
from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.formatting.rule import CellIsRule, FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .formatting import (
    BLUE, BLUE_FILL, INK, INK_SOFT, PANEL, RED, RED_FILL, excel_formats,
)

HEADER_FILL = PatternFill("solid", fgColor=INK)
HEADER_FONT = Font(bold=True, color="FFFFFF")
WEAK_FILL = PatternFill("solid", fgColor=RED_FILL)
WEAK_FONT = Font(color="9C1C1C")

GROUP_COLUMNS = [
    "campaigns", "impressions", "clicks", "conversions", "spend", "revenue",
    "ctr", "conversion_rate", "cpc", "cost_per_conversion", "roas", "roi", "roas_vs_avg",
]
CAMPAIGN_COLUMNS = [
    "campaign", "channel", "segment", "platform", "duration", "date", "impressions", "clicks",
    "conversions", "spend", "revenue", "ctr", "conversion_rate", "cpc",
    "cost_per_conversion", "roas", "roi", "quality_flag",
]


def write_table(ws, df, columns, formats, start_row=1, autofilter=True):
    """Write a styled table and return (header_row, last_row, {column: letter})."""
    columns = [c for c in columns if c in df.columns]
    letters = {}
    for i, col in enumerate(columns, start=1):
        label = formats.get(col, (col.replace("_", " ").title(), None))[0]
        cell = ws.cell(row=start_row, column=i, value=label)
        cell.fill, cell.font = HEADER_FILL, HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        letters[col] = get_column_letter(i)
        width = max(len(label), *(len(str(v)) for v in df[col].head(50))) + 2
        ws.column_dimensions[letters[col]].width = min(max(width, 10), 40)
    ws.row_dimensions[start_row].height = 32

    for r, row in enumerate(df[columns].itertuples(index=False), start=start_row + 1):
        for c, value in enumerate(row, start=1):
            if value != value:  # NaN
                value = None
            elif isinstance(value, np.generic):  # numpy scalar -> plain python
                value = value.item()
            ws.cell(row=r, column=c, value=value)

    last_row = start_row + len(df)
    for col in columns:
        fmt = formats.get(col, (None, None))[1]
        if fmt:
            for (cell,) in ws[f"{letters[col]}{start_row + 1}:{letters[col]}{last_row}"]:
                cell.number_format = fmt
    if autofilter and len(df):
        ws.auto_filter.ref = f"A{start_row}:{get_column_letter(len(columns))}{last_row}"
    ws.freeze_panes = ws.cell(row=start_row + 1, column=2)
    return start_row, last_row, letters


def highlight_below(ws, letter, first, last, threshold):
    """Red fill on values below the threshold (weak performers)."""
    ws.conditional_formatting.add(
        f"{letter}{first}:{letter}{last}",
        CellIsRule(operator="lessThan", formula=[repr(float(threshold))], fill=WEAK_FILL, font=WEAK_FONT),
    )


def add_bar_chart(ws, title, y_title, cats, values, anchor, height=7.5, width=16):
    chart = BarChart()
    chart.type = "bar"
    chart.title = title
    chart.y_axis.title = y_title
    chart.y_axis.scaling.min = 0  # zero baseline so small gaps aren't exaggerated
    chart.y_axis.majorGridlines = None
    chart.x_axis.delete = False
    chart.y_axis.delete = False
    chart.legend = None
    chart.add_data(values, titles_from_data=True)
    chart.set_categories(cats)
    chart.series[0].graphicalProperties.solidFill = BLUE
    chart.series[0].graphicalProperties.line.noFill = True
    chart.x_axis.scaling.orientation = "maxMin"  # keep the table's order, best at top
    chart.height, chart.width = height, width
    ws.add_chart(chart, anchor)


def group_sheet(wb, name, table, label_col, noun, overall_roas, formats):
    ws = wb.create_sheet(name)
    header, last, letters = write_table(ws, table, [label_col] + GROUP_COLUMNS, formats)
    highlight_below(ws, letters["roas"], header + 1, last, overall_roas)
    highlight_below(ws, letters["roas_vs_avg"], header + 1, last, 0)
    note_row = last + 2
    ws.cell(row=note_row, column=1,
            value="Red = return on ad spend below the overall average.").font = Font(italic=True, color=INK_SOFT)
    if label_col == "platform":
        ws.cell(row=note_row + 1, column=1,
                value="A campaign on several platforms counts once for each, so totals overlap.").font = Font(
            italic=True, color=INK_SOFT)
    col = ws[letters["roas"]][0].column
    add_bar_chart(
        ws, f"ROAS by {noun}", "Revenue per 1 spent",
        Reference(ws, min_col=1, min_row=header + 1, max_row=last),
        Reference(ws, min_col=col, min_row=header, max_row=last),
        f"B{note_row + 3}",
    )
    return ws


def wrapped_lines(text, width_px, font_px=15):
    """How many lines text takes in a wrapped cell, measured with the real font.

    Falls back to a character estimate if Calibri isn't available.
    """
    try:
        from PIL import ImageFont
        font = ImageFont.truetype("calibri.ttf", font_px)
    except (ImportError, OSError):
        return max(1, -(-len(text) // int(width_px / 6.6)))
    lines, current = 1, ""
    for word in text.split():
        trial = f"{current} {word}".strip()
        if font.getlength(trial) > width_px and current:
            lines, current = lines + 1, word
        else:
            current = trial
    return lines


def summary_sheet(wb, data, cfg, ai_summary):
    ws = wb.active
    ws.title = "Summary"
    ws.sheet_view.showGridLines = False
    cur = cfg["currency"]
    o = data.overall
    for col in "ABCDEFGHI":
        ws.column_dimensions[col].width = 15
    ws.column_dimensions["A"].width = 3

    ws["B2"] = cfg["report"]["title"]
    ws["B2"].font = Font(size=20, bold=True, color=INK)
    period = ""
    if data.date_range:
        period = f"{data.date_range[0]:%d %b %Y} to {data.date_range[1]:%d %b %Y} · "
    ws["B3"] = f"{period}{o['campaigns']:,} campaigns · source: {data.source} · run {date.today():%d %b %Y}"
    ws["B3"].font = Font(color=INK_SOFT)

    # (label, number, Excel format): real numbers so Excel can use them
    crore = f'"{cur}"#,##0.0" Cr"'
    cards = [
        ("Revenue", o["revenue"] / 1e7, crore), ("Spend", o["spend"] / 1e7, crore),
        ("ROAS", o["roas"], '0.00"x"'), ("ROI", o["roi"], "0%"),
        ("Click-through rate", o["ctr"], "0.00%"), ("Conversion rate", o["conversion_rate"], "0.0%"),
        ("Cost per click", o["cpc"], f'"{cur}"#,##0.00'),
        ("Cost per conversion", o["cost_per_conversion"], f'"{cur}"#,##0'),
    ]
    card_fill = PatternFill("solid", fgColor=PANEL)
    for i, (label, value, number_format) in enumerate(cards):
        row = 5 + (i // 4) * 3
        col = 2 + (i % 4) * 2
        ws.merge_cells(start_row=row, start_column=col, end_row=row, end_column=col + 1)
        ws.merge_cells(start_row=row + 1, start_column=col, end_row=row + 1, end_column=col + 1)
        top, bottom = ws.cell(row=row, column=col), ws.cell(row=row + 1, column=col)
        top.value, bottom.value = label, float(value)
        bottom.number_format = number_format
        bottom.alignment = Alignment(horizontal="left")
        top.font = Font(size=10, color=INK_SOFT)
        bottom.font = Font(size=18, bold=True, color=BLUE if label == "ROAS" else INK)
        for r in (row, row + 1):
            for c in (col, col + 1):
                ws.cell(row=r, column=c).fill = card_fill
        ws.row_dimensions[row + 1].height = 30

    row = 12
    # merged B:I is 8 columns of width 15, about 110 px each, less cell padding
    text_width_px = 8 * 110 - 10

    def section(title, lines, numbered=True):
        nonlocal row
        ws.cell(row=row, column=2, value=title).font = Font(size=14, bold=True, color=INK)
        row += 1
        for i, line in enumerate(lines, start=1):
            ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=9)
            text = f"{i}. {line}" if numbered else line
            cell = ws.cell(row=row, column=2, value=text)
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            # same padding under every item so the gaps are even
            ws.row_dimensions[row].height = 15 * wrapped_lines(text, text_width_px) + 6
            row += 1
        row += 1

    if ai_summary:
        section("Executive summary", [ai_summary], numbered=False)
    section("Key findings", data.insights.findings)
    section("Recommendations", data.insights.recommendations)
    ws.cell(row=row, column=2,
            value="ROAS = revenue ÷ spend. ROI = (revenue − spend) ÷ spend. "
                  "Group figures are calculated from totals, not averages of campaigns.").font = Font(
        italic=True, color=INK_SOFT)


def weekly_sheet(wb, weekly, formats, threshold):
    ws = wb.create_sheet("Weekly Trend")
    cols = ["week", "campaigns", "spend", "revenue", "roas", "revenue_change", "roas_change",
            "partial", "anomaly", "note"]
    header, last, letters = write_table(ws, weekly, cols, formats)
    ws.column_dimensions[letters["note"]].width = 42
    # whole row red when flagged
    rng = f"A{header + 1}:{letters['note']}{last}"
    ws.conditional_formatting.add(
        rng, FormulaRule(formula=[f"${letters['anomaly']}{header + 1}=TRUE"], fill=WEAK_FILL, font=WEAK_FONT)
    )
    ws.cell(row=last + 2, column=1,
            value=f"Red = moved more than {threshold:.0%} vs the previous full week. "
                  "Partial weeks are shown but not flagged.").font = Font(italic=True, color=INK_SOFT)

    chart = LineChart()
    chart.title = "Weekly revenue"
    chart.y_axis.title = "Revenue"
    chart.y_axis.number_format = "#,##0"
    chart.x_axis.number_format = "dd mmm"
    chart.x_axis.delete = False
    chart.y_axis.delete = False
    chart.legend = None
    rev_col = ws[letters["revenue"]][0].column
    chart.add_data(Reference(ws, min_col=rev_col, min_row=header, max_row=last), titles_from_data=True)
    chart.set_categories(Reference(ws, min_col=1, min_row=header + 1, max_row=last))
    chart.series[0].graphicalProperties.line.solidFill = BLUE
    chart.series[0].graphicalProperties.line.width = 22000
    chart.height, chart.width = 8, 22
    ws.add_chart(chart, f"B{last + 4}")


def outliers_sheet(wb, data, cfg, formats):
    """Action list (low-return outliers, biggest loss first), then the other outliers."""
    ws = wb.create_sheet("Outliers")
    th = cfg["thresholds"]
    method = cfg["outlier_method"]
    if method == "log_iqr":
        how = (f"Log IQR method: within each channel, flagged when log(ROAS) or log(cost per conversion) is more "
               f"than {th['iqr_multiplier']:g}x the interquartile range beyond Q1/Q3.")
    elif method == "iqr":
        how = (f"IQR method: within each channel, flagged when ROI or cost per conversion is more than "
               f"{th['iqr_multiplier']:g}x the interquartile range beyond Q1/Q3.")
    else:
        how = (f"Z-score method: within each channel, flagged when more than {th['outlier_z']:g} "
               "standard deviations from the mean.")
    ws["A1"] = how + " Score = how far past the limit, in IQRs (or std devs). Channel floor = lowest normal ROAS."
    ws["A1"].font = Font(italic=True, color=INK_SOFT)

    action = data.action_list
    ws["A3"] = f"Action list: {len(action):,} campaigns with unusually low return, biggest loss first"
    ws["A3"].font = Font(size=13, bold=True, color=RED)
    cols = ["campaign", "channel", "segment", "spend", "revenue", "loss", "roas", "roas_lower_limit",
            "cost_per_conversion", "return_score", "reason"]
    header, last, letters = write_table(ws, action, cols, formats, start_row=4, autofilter=False)
    if len(action):
        highlight_below(ws, letters["return_score"], header + 1, last, 0)
    first_freeze = ws.freeze_panes

    others = data.outliers[data.outliers["outlier_type"] != "Low return"] if len(data.outliers) else data.outliers
    start = last + 3
    title = f"Other outliers: {len(others):,} (unusually high return or unusual cost per conversion)"
    ws.cell(row=start - 1, column=1, value=title).font = Font(size=13, bold=True, color=INK)
    cols = ["campaign", "channel", "segment", "spend", "revenue", "outlier_type", "roas",
            "cost_per_conversion", "return_score", "cost_score", "reason"]
    write_table(ws, others, cols, formats, start_row=start, autofilter=False)
    ws.freeze_panes = first_freeze
    ws.column_dimensions["K"].width = 70


def write_excel(data, path, cfg, ai_summary=None):
    formats = excel_formats(cfg["currency"])
    avg = data.overall["roas"]
    wb = Workbook()
    summary_sheet(wb, data, cfg, ai_summary)

    group_sheet(wb, "By Channel", data.by_channel, "channel", "channel", avg, formats)
    if data.by_segment is not None:
        group_sheet(wb, "By Segment", data.by_segment, "segment", "segment", avg, formats)
    if data.by_duration is not None:
        table = data.by_duration.assign(duration_band=data.by_duration["duration_band"].astype(str))
        group_sheet(wb, "By Duration", table, "duration_band", "campaign length", avg, formats)
    if data.by_platform is not None:
        group_sheet(wb, "By Platform", data.by_platform, "platform", "platform", avg, formats)

    # top and bottom campaigns
    ws = wb.create_sheet("By Campaign")
    n = len(data.top)
    ws["A1"] = f"Top {n} campaigns by ROI"
    ws["A1"].font = Font(size=13, bold=True, color=BLUE)
    cols = [c for c in CAMPAIGN_COLUMNS if c != "quality_flag"]
    _, last, letters = write_table(ws, data.top, cols, formats, start_row=2, autofilter=False)
    start = last + 3
    ws.cell(row=start - 1, column=1, value=f"Bottom {n} campaigns by ROI").font = Font(size=13, bold=True, color=RED)
    header, last, letters = write_table(ws, data.bottom, cols, formats, start_row=start, autofilter=False)
    highlight_below(ws, letters["roi"], 3, last, 0)
    ws.freeze_panes = "B3"

    outliers_sheet(wb, data, cfg, formats)

    if data.weekly is not None:
        weekly_sheet(wb, data.weekly, formats, cfg["thresholds"]["week_change"])

    ws = wb.create_sheet("Data Quality")
    ws["A1"] = f"Rows in: {data.quality.rows_in:,}   Rows out: {data.quality.rows_out:,}   " \
               f"Removed: {data.quality.rows_removed:,}"
    ws["A1"].font = Font(bold=True)
    q = data.quality.as_frame()
    header, last, letters = write_table(ws, q, ["check", "found", "action"],
                                        {"check": ("Check", None), "found": ("Found", "#,##0"),
                                         "action": ("Action", None)}, start_row=3)
    ws.column_dimensions["A"].width = 44
    ws.column_dimensions["C"].width = 32

    ws = wb.create_sheet("All Campaigns")
    header, last, letters = write_table(ws, data.campaigns, CAMPAIGN_COLUMNS, formats)
    highlight_below(ws, letters["roi"], header + 1, last, 0)

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path
