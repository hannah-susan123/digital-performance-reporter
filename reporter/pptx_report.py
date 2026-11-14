"""PowerPoint deck: one finding per slide, titles that state the finding."""
from datetime import date

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

from .formatting import BLUE, INK, INK_SOFT, PANEL, RED, SURFACE, money, pct

FONT = "Segoe UI"
CHART_W = 7.7  # charts are 10 x 5.6, so height follows


def rgb(hex_code):
    return RGBColor.from_string(hex_code)


class Deck:
    def __init__(self, cfg, footer):
        self.prs = Presentation()
        self.prs.slide_width, self.prs.slide_height = Inches(13.333), Inches(7.5)
        self.cfg = cfg
        self.footer = footer

    # building blocks
    def text(self, slide, x, y, w, h, text, size=14, bold=False, color=INK, align=None,
             anchor=MSO_ANCHOR.TOP):
        box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = box.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = anchor
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
        p = tf.paragraphs[0]
        if align:
            p.alignment = align
        run = p.add_run()
        run.text = text
        run.font.size, run.font.bold, run.font.name = Pt(size), bold, FONT
        run.font.color.rgb = rgb(color)
        return box

    def lines(self, slide, x, y, w, h, items, size=15, marker="•", gap=10):
        box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = box.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_right = 0
        for i, item in enumerate(items):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.space_after = Pt(gap)
            lead = f"{i + 1}." if marker == "number" else marker
            for text, bold, color in [(f"{lead}  ", True, BLUE), (item, False, INK)]:
                run = p.add_run()
                run.text = text
                run.font.size, run.font.bold, run.font.name = Pt(size), bold, FONT
                run.font.color.rgb = rgb(color)
        return box

    def rect(self, slide, x, y, w, h, fill, shape=MSO_SHAPE.RECTANGLE):
        s = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
        s.fill.solid()
        s.fill.fore_color.rgb = rgb(fill)
        s.line.fill.background()
        s.shadow.inherit = False
        return s

    def new_slide(self, title, notes=""):
        slide = self.prs.slides.add_slide(self.prs.slide_layouts[6])  # blank
        slide.background.fill.solid()
        slide.background.fill.fore_color.rgb = rgb(SURFACE)
        number = len(self.prs.slides)
        if title:
            self.rect(slide, 0.6, 0.42, 0.7, 0.07, BLUE)
            self.text(slide, 0.6, 0.6, 12.1, 0.95, title, size=26, bold=True, anchor=MSO_ANCHOR.TOP)
        self.text(slide, 0.6, 7.0, 10, 0.3, self.footer, size=9, color=INK_SOFT)
        self.text(slide, 11.9, 7.0, 0.8, 0.3, str(number), size=9, color=INK_SOFT, align=PP_ALIGN.RIGHT)
        if notes:
            slide.notes_slide.notes_text_frame.text = notes
        return slide

    def chart(self, slide, path, x=0.5, y=1.65):
        slide.shapes.add_picture(str(path), Inches(x), Inches(y), width=Inches(CHART_W))

    def side_panel(self, slide, heading, items):
        self.rect(slide, 8.55, 1.75, 4.2, 4.9, PANEL)
        self.text(slide, 8.85, 1.95, 3.7, 0.4, heading, size=14, bold=True, color=INK_SOFT)
        self.lines(slide, 8.85, 2.5, 3.7, 4.0, items, size=14, gap=12)

    def table(self, slide, x, y, w, rows, header, col_widths, highlight=BLUE):
        shape = slide.shapes.add_table(len(rows) + 1, len(header), Inches(x), Inches(y),
                                       Inches(w), Inches(0.32 * (len(rows) + 1)))
        t = shape.table
        for c, width in enumerate(col_widths):
            t.columns[c].width = Inches(width)
        for r, values in enumerate([header] + rows):
            for c, value in enumerate(values):
                cell = t.cell(r, c)
                cell.text = str(value)
                cell.margin_left = cell.margin_right = Inches(0.08)
                cell.fill.solid()
                cell.fill.fore_color.rgb = rgb(highlight if r == 0 else ("FFFFFF" if r % 2 else PANEL))
                para = cell.text_frame.paragraphs[0]
                para.alignment = PP_ALIGN.RIGHT if c == len(values) - 1 else PP_ALIGN.LEFT
                for run in para.runs:
                    run.font.size, run.font.name = Pt(11), FONT
                    run.font.bold = r == 0
                    run.font.color.rgb = rgb("FFFFFF" if r == 0 else INK)
        return t

    def save(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.prs.save(path)
        return path


def group_points(table, label_col, cur):
    ranked = table.sort_values("roas", ascending=False)
    best, worst = ranked.iloc[0], ranked.iloc[-1]
    cheapest = table.loc[table["cost_per_conversion"].idxmin()]
    return [
        f"Best: {best[label_col]} returns {cur}{best['roas']:.2f} per {cur}1 "
        f"({best['roas_vs_avg']:+.1%} vs average).",
        f"Weakest: {worst[label_col]} returns {cur}{worst['roas']:.2f} ({worst['roas_vs_avg']:+.1%}).",
        f"Gap between best and weakest: {pct(best['roas'] / worst['roas'] - 1)}.",
        f"Lowest cost per conversion: {cheapest[label_col]} at {cur}{cheapest['cost_per_conversion']:.0f}.",
    ]


def write_pptx(data, charts, path, cfg, ai_summary=None):
    cur = cfg["currency"]
    o = data.overall
    titles = data.insights.titles
    period = ""
    if data.date_range:
        period = f"{data.date_range[0]:%d %b %Y} – {data.date_range[1]:%d %b %Y}"
    deck = Deck(cfg, f"Source: {data.source}" + (f" · {period}" if period else ""))

    # 1. title
    s = deck.new_slide(None)
    deck.rect(s, 0, 0, 0.35, 7.5, BLUE)
    deck.text(s, 1.0, 2.0, 11, 1.2, cfg["report"]["title"], size=40, bold=True)
    deck.text(s, 1.0, 3.25, 11, 0.8, "Which channels and segments give the best return on spend?",
              size=22, color=BLUE)
    meta = f"{o['campaigns']:,} campaigns" + (f" · {period}" if period else "")
    deck.text(s, 1.0, 4.4, 11, 0.5, meta, size=16, color=INK_SOFT)
    deck.text(s, 1.0, 4.85, 11, 0.5, f"Report run {date.today():%d %B %Y}", size=16, color=INK_SOFT)

    # 2. KPI overview
    notes = ai_summary or "Executive summary: run with --ai to add one here."
    s = deck.new_slide(titles["kpi"], notes=notes)
    cards = [
        ("Revenue", money(o["revenue"], cur)), ("Spend", money(o["spend"], cur)),
        ("Return on ad spend", f"{cur}{o['roas']:.2f} per {cur}1"), ("ROI", pct(o["roi"], 0)),
        ("Click-through rate", pct(o["ctr"], 2)), ("Conversion rate", pct(o["conversion_rate"], 1)),
        ("Cost per click", f"{cur}{o['cpc']:,.2f}"), ("Cost per conversion", f"{cur}{o['cost_per_conversion']:,.0f}"),
    ]
    for i, (label, value) in enumerate(cards):
        x, y = 0.6 + (i % 4) * 3.07, 1.85 + (i // 4) * 1.95
        deck.rect(s, x, y, 2.82, 1.65, PANEL)
        deck.text(s, x + 0.25, y + 0.25, 2.4, 0.35, label, size=13, color=INK_SOFT)
        deck.text(s, x + 0.25, y + 0.7, 2.4, 0.7, value, size=26, bold=True,
                  color=BLUE if label == "Return on ad spend" else INK)
    deck.text(s, 0.6, 5.95, 12, 0.7,
              f"ROAS = revenue ÷ spend.  ROI = (revenue − spend) ÷ spend.  "
              f"{o['campaigns']:,} campaigns, {data.quality.rows_removed:,} rows removed in cleaning.",
              size=12, color=INK_SOFT)

    # 3. channels
    s = deck.new_slide(titles["channel"])
    deck.chart(s, charts["channel"])
    deck.side_panel(s, "What the numbers say", group_points(data.by_channel, "channel", cur))

    # 4. segments
    if data.by_segment is not None:
        s = deck.new_slide(titles["segment"])
        deck.chart(s, charts["segment"])
        deck.side_panel(s, "What the numbers say", group_points(data.by_segment, "segment", cur))

    # 5. top and bottom campaigns
    s = deck.new_slide(titles["campaigns"])
    deck.chart(s, charts["campaigns"], x=0.4)
    header = ["Campaign", "Channel", "ROAS"]
    widths = [1.55, 1.45, 1.1]
    top = [[r.campaign, r.channel, f"{cur}{r.roas:.1f}"] for r in data.top.head(5).itertuples()]
    bottom = [[r.campaign, r.channel, f"{cur}{r.roas:.2f}"] for r in data.bottom.head(5).itertuples()]
    deck.text(s, 8.55, 1.7, 4.1, 0.35, "Top 5 campaigns", size=13, bold=True, color=BLUE)
    deck.table(s, 8.55, 2.05, 4.1, top, header, widths)
    deck.text(s, 8.55, 4.2, 4.1, 0.35, "Bottom 5 campaigns", size=13, bold=True, color=RED)
    deck.table(s, 8.55, 4.55, 4.1, bottom, header, widths, highlight=RED)

    # 6. weekly trend
    if data.weekly is not None:
        w = data.weekly
        flagged = w[w["anomaly"]]
        points = [f"Week of {r.week:%d %b %Y}: {r.note}." for r in flagged.head(3).itertuples()]
        if not points:
            points = [f"No full week moved more than {pct(cfg['thresholds']['week_change'], 0)}."]
        points.append(f"{int(w['partial'].sum())} partial weeks (start/end of data or low volume) "
                      "are shown in grey and not flagged.")
        s = deck.new_slide(titles["weekly"])
        deck.chart(s, charts["weekly"])
        deck.side_panel(s, "Alerts", points)

    # 7. findings
    s = deck.new_slide(titles["findings"],
                       notes="Each finding comes from a simple rule applied to the KPI tables.")
    deck.lines(s, 0.6, 1.75, 12.1, 5.1, data.insights.findings, size=16, marker="number", gap=14)

    # 8. recommendations
    s = deck.new_slide(titles["recommendations"])
    for i, rec in enumerate(data.insights.recommendations[:4]):
        y = 1.8 + i * 1.25
        circle = deck.rect(s, 0.6, y, 0.6, 0.6, BLUE, shape=MSO_SHAPE.OVAL)
        tf = circle.text_frame
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        tf.text = str(i + 1)
        run = tf.paragraphs[0].runs[0]
        run.font.size, run.font.bold, run.font.name = Pt(18), True, FONT
        run.font.color.rgb = rgb("FFFFFF")
        tf.paragraphs[0].alignment = PP_ALIGN.CENTER
        deck.text(s, 1.5, y - 0.02, 11.2, 1.1, rec, size=17, anchor=MSO_ANCHOR.TOP)

    return deck.save(path)
