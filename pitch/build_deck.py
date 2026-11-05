"""Builds Drift-intro.pptx. Run: api/.venv/bin/python pitch/build_deck.py"""

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

HERE = Path(__file__).resolve().parent
FONT = "Helvetica Neue"
MONO = "Menlo"

BG = RGBColor(0x09, 0x09, 0x0B)
CARD = RGBColor(0x13, 0x13, 0x16)
BORDER = RGBColor(0x27, 0x27, 0x2A)
WHITE = RGBColor(0xFA, 0xFA, 0xFA)
TEXT = RGBColor(0xD4, 0xD4, 0xD8)
MUTED = RGBColor(0xA1, 0xA1, 0xAA)
DIM = RGBColor(0x71, 0x71, 0x7A)
EMERALD = RGBColor(0x34, 0xD3, 0x99)
EMERALD_BG = RGBColor(0x0B, 0x24, 0x1B)
AMBER = RGBColor(0xFB, 0xBF, 0x24)
AMBER_BG = RGBColor(0x2A, 0x1F, 0x07)
ROSE = RGBColor(0xFB, 0x71, 0x85)
ROSE_BG = RGBColor(0x2A, 0x10, 0x15)
SKY = RGBColor(0x7D, 0xD3, 0xFC)
SKY_BG = RGBColor(0x0A, 0x1F, 0x2B)
VIOLET = RGBColor(0xC4, 0xB5, 0xFD)
VIOLET_BG = RGBColor(0x1C, 0x16, 0x2E)
ZINC_BG = RGBColor(0x1C, 0x1C, 0x20)

prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
BLANK = prs.slide_layouts[6]


def slide(notes: str):
    s = prs.slides.add_slide(BLANK)
    s.background.fill.solid()
    s.background.fill.fore_color.rgb = BG
    s.notes_slide.notes_text_frame.text = notes
    return s


def text(s, x, y, w, h, runs, size=18, color=TEXT, bold=False, align=PP_ALIGN.LEFT, font=FONT,
         anchor=MSO_ANCHOR.TOP, spacing=1.15):
    """runs: str, or list of paragraphs; each paragraph is a str or list of (text, overrides) tuples."""
    box = s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    paras = runs if isinstance(runs, list) else [runs]
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = spacing
        for chunk in (para if isinstance(para, list) else [(para, {})]):
            t, o = chunk if isinstance(chunk, tuple) else (chunk, {})
            r = p.add_run()
            r.text = t
            f = r.font
            f.name = o.get("font", font)
            f.size = Pt(o.get("size", size))
            f.bold = o.get("bold", bold)
            f.color.rgb = o.get("color", color)
    return box


def box(s, x, y, w, h, fill=CARD, line=BORDER, radius=0.08, weight=1):
    shp = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    shp.adjustments[0] = radius
    shp.fill.solid()
    shp.fill.fore_color.rgb = fill
    if line is None:
        shp.line.fill.background()
    else:
        shp.line.color.rgb = line
        shp.line.width = Pt(weight)
    shp.shadow.inherit = False
    return shp


def pill(s, x, y, label, fg, bg, w=1.1, size=11):
    b = box(s, x, y, w, 0.32, fill=bg, line=fg, radius=0.5, weight=0.75)
    tf = b.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = label
    r.font.name, r.font.size, r.font.bold, r.font.color.rgb = FONT, Pt(size), True, fg
    return b


def dot(s, x, y, color, d=0.14):
    c = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x), Inches(y), Inches(d), Inches(d))
    c.fill.solid()
    c.fill.fore_color.rgb = color
    c.line.fill.background()
    c.shadow.inherit = False


def arrow(s, x, y, w=0.4, color=DIM):
    a = s.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Inches(x), Inches(y), Inches(w), Inches(0.26))
    a.fill.solid()
    a.fill.fore_color.rgb = color
    a.line.fill.background()
    a.shadow.inherit = False


def eyebrow(s, label, y=0.7):
    text(s, 0.9, y, 8, 0.3, label.upper(), size=12, color=EMERALD, bold=True)


def title(s, t, y=1.05, size=38):
    text(s, 0.9, y, 11.5, 1.0, t, size=size, color=WHITE, bold=True)


def footer(s, n):
    text(s, 0.9, 6.95, 6, 0.3, [[("Drift", {"bold": True, "color": MUTED}),
                                 ("  ·  the Company Brain that notices when it is wrong", {})]], size=10, color=DIM)
    text(s, 11.4, 6.95, 1.0, 0.3, f"{n:02d}", size=10, color=DIM, align=PP_ALIGN.RIGHT)


# 1 ─ Title
s = slide("Hi, this is Drift: a Company Brain that notices when it's wrong. "
          "In the next few minutes I'll show you why company knowledge silently goes stale, "
          "and how Drift uses TriggerWare to catch it the moment it happens.")
logo = box(s, 0.9, 2.15, 0.8, 0.8, fill=EMERALD_BG, line=EMERALD, radius=0.25)
dot(s, 1.2, 2.45, EMERALD, d=0.2)
text(s, 0.9, 1.35, 10, 0.35, "COMPANY BRAIN HACKATHON  ·  2026", size=12, color=DIM, bold=True)
text(s, 0.9, 3.15, 11, 1.4, "Drift", size=96, color=WHITE, bold=True, spacing=1.0)
text(s, 0.9, 4.75, 11, 0.7, "The Company Brain that notices when it is wrong.", size=30, color=TEXT)
b = box(s, 0.9, 5.75, 4.6, 0.5, fill=EMERALD_BG, line=EMERALD, radius=0.5, weight=0.75)
dot(s, 1.15, 5.93, EMERALD)
text(s, 1.42, 5.83, 4.0, 0.35, [[("Live verification powered by ", {}), ("TriggerWare", {"bold": True})]],
     size=15, color=EMERALD)

# 2 ─ Problem
s = slide("Every company has a runbook that's quietly wrong. This one says Apollo uses MongoDB, "
          "weeks after the team migrated to PostgreSQL. Nobody lied; reality moved and the document didn't. "
          "And today's tools make it worse: search finds the stale page instantly, AI assistants repeat it "
          "with confidence, and AI memory only changes its mind when someone corrects it. Nobody is checking.")
eyebrow(s, "The problem")
title(s, "Company knowledge quietly goes stale.")
box(s, 0.9, 2.35, 5.9, 2.0)
text(s, 1.2, 2.6, 4.5, 0.3, "Apollo runbook  ·  last edited Feb 10", size=12, color=DIM, bold=True)
pill(s, 5.5, 2.55, "STALE", AMBER, AMBER_BG, w=1.0)
text(s, 1.2, 3.1, 5.3, 1.1, "“Apollo uses MongoDB as its primary datastore. If latency spikes, "
     "check the MongoDB replica set.”", size=17, color=TEXT)
box(s, 0.9, 4.55, 5.9, 1.25, fill=EMERALD_BG, line=EMERALD, weight=0.75)
text(s, 1.2, 4.75, 5.4, 0.3, "LIVE SERVICE CATALOG  ·  RIGHT NOW", size=11, color=EMERALD, bold=True)
text(s, 1.2, 5.1, 5.4, 0.5, [[("apollo  →  ", {"font": MONO, "color": MUTED}),
                              ("PostgreSQL", {"font": MONO, "bold": True, "color": WHITE})]], size=20)
for i, (head, sub) in enumerate([
    ("Search finds the stale page instantly.", "Glean-style search ranks it, cites it, trusts it."),
    ("AI assistants repeat it with confidence.", "An agent reads the runbook and answers “MongoDB”."),
    ("Memory only updates when corrected.", "Agent memory changes only if someone says so."),
]):
    y = 2.4 + i * 1.05
    dot(s, 7.4, y + 0.12, ROSE)
    text(s, 7.75, y, 4.8, 0.4, head, size=19, color=WHITE, bold=True)
    text(s, 7.75, y + 0.42, 4.8, 0.4, sub, size=14, color=MUTED)
text(s, 7.4, 5.55, 5.2, 0.5, "Nobody is checking.", size=26, color=ROSE, bold=True)
footer(s, 2)

# 3 ─ Gap
s = slide("There are great tools for finding company knowledge, like Glean and Atlassian Rovo, "
          "and for giving AI agents memory, like Zep and Mem0. But none of them check whether what they "
          "store is still true. That's the gap Drift fills. We're not a better Glean; we're the missing "
          "layer that keeps any Company Brain honest.")
eyebrow(s, "The gap")
title(s, "Everyone stores knowledge. Nobody verifies it.", size=34)
cols = [
    ("FIND IT", "Glean  ·  Atlassian Rovo", "Search and answers over company knowledge.",
     "Retrieves whatever the page says.", False),
    ("REMEMBER IT", "Zep / Graphiti  ·  Mem0", "Long-term memory for AI agents.",
     "Changes only when fed a contradiction.", False),
    ("VERIFY IT", "Drift", "Continuously checks facts against the live systems that run the company.",
     "Notices on its own when reality moves.", True),
]
for i, (tag, who, what, gap, hero) in enumerate(cols):
    x = 0.9 + i * 3.95
    box(s, x, 2.4, 3.7, 3.55, fill=EMERALD_BG if hero else CARD, line=EMERALD if hero else BORDER,
        weight=1.5 if hero else 1)
    text(s, x + 0.35, 2.7, 3.0, 0.3, tag, size=12, color=EMERALD if hero else DIM, bold=True)
    text(s, x + 0.35, 3.1, 3.0, 0.5, who, size=22 if hero else 19, color=WHITE, bold=True)
    text(s, x + 0.35, 3.75, 3.0, 1.1, what, size=15, color=TEXT)
    text(s, x + 0.35, 5.0, 3.0, 0.8, gap, size=14, color=EMERALD if hero else ROSE, bold=True)
text(s, 0.9, 6.25, 11.5, 0.5, "Drift isn’t a better Glean. It’s the missing layer that keeps any Company Brain honest.",
     size=17, color=MUTED)
footer(s, 3)

# 4 ─ How it works
s = slide("Here's how Drift works. First it learns: docs, decisions and chat become facts, each with a source, "
          "how much to trust it, and when it was true. Small talk and secrets are thrown away. "
          "Second, every fact Drift can check becomes a TriggerWare trigger: a scheduled SQL query against the "
          "live system. Third, when reality changes, TriggerWare pushes only the rows that changed. "
          "And fourth, Drift reacts: it updates memory without erasing history, flags documents that are now "
          "wrong, traces what depends on the change, and alerts the owner. Then it keeps doing that, on its own.")
eyebrow(s, "How it works")
title(s, "A memory that keeps checking itself.")
steps = [
    ("1", "LEARN", "Docs, decisions and chat become facts with a source, a trust level and a time range. "
                   "Small talk and secrets are dropped.", MUTED),
    ("2", "WATCH", "Every checkable fact becomes a TriggerWare trigger: scheduled SQL against the live system.",
     EMERALD),
    ("3", "DETECT", "When reality changes, TriggerWare pushes only the rows that changed.", EMERALD),
    ("4", "REACT", "Update memory and keep history. Flag stale docs, trace what depends on it, alert the owner.",
     MUTED),
]
for i, (n, head, body, accent) in enumerate(steps):
    x = 0.9 + i * 3.05
    box(s, x, 2.45, 2.65, 3.3, line=EMERALD if accent == EMERALD else BORDER)
    text(s, x + 0.3, 2.7, 2.1, 0.6, n, size=34, color=accent, bold=True)
    text(s, x + 0.3, 3.4, 2.1, 0.35, head, size=15, color=WHITE, bold=True)
    text(s, x + 0.3, 3.85, 2.1, 1.8, body, size=13.5, color=TEXT)
    if i < 3:
        arrow(s, x + 2.7, 3.95, w=0.3)
text(s, 0.9, 6.05, 11.5, 0.45,
     [[("↻  ", {"color": EMERALD, "bold": True}),
       ("Runs continuously, on its own schedule. Nobody has to remember to update the docs.", {})]],
     size=16, color=MUTED)
pill(s, 3.95, 5.45, "TriggerWare", EMERALD, EMERALD_BG, w=1.4)
pill(s, 7.0, 5.45, "TriggerWare", EMERALD, EMERALD_BG, w=1.4)
footer(s, 4)

# 5 ─ TriggerWare
s = slide("TriggerWare is the engine of this loop. It does three jobs. It lets Drift read live systems as plain SQL "
          "tables. It watches for changes and pushes only what's different: here, Apollo's trigger saw MongoDB "
          "removed and PostgreSQL added, and that single row change is what sets everything else off. "
          "And it lets Drift re-check a fact in the middle of answering a question. Without TriggerWare we'd write "
          "a scraper and a change detector for every source; with it, adding a source is one connector.")
eyebrow(s, "Powered by TriggerWare")
title(s, "TriggerWare is the engine of the loop.")
jobs = [
    ("Reads live systems as SQL", "The service catalog becomes a table Drift can query."),
    ("Detects change, pushes the delta", "One trigger per fact. Drift never scrapes or diffs."),
    ("Checks live, mid-answer", "Before answering, Drift re-runs that fact’s query."),
]
for i, (head, sub) in enumerate(jobs):
    y = 2.4 + i * 1.1
    pill(s, 0.9, y + 0.04, f"0{i + 1}", EMERALD, EMERALD_BG, w=0.6)
    text(s, 1.75, y, 4.6, 0.4, head, size=19, color=WHITE, bold=True)
    text(s, 1.75, y + 0.42, 4.6, 0.4, sub, size=14, color=MUTED)
box(s, 6.75, 2.35, 5.7, 3.35, fill=RGBColor(0x0D, 0x0D, 0x10))
text(s, 7.05, 2.6, 5.2, 0.3, "TRIGGER  ·  drift_acme_apollo_uses", size=11, color=DIM, bold=True)
text(s, 7.05, 3.0, 5.2, 0.9, [[("SELECT ", {"color": SKY}), ("datastore ", {}), ("FROM ", {"color": SKY}),
                               ("service_catalog", {})],
                              [("WHERE ", {"color": SKY}), ("org = 'acme' ", {}), ("AND ", {"color": SKY}),
                               ("service = 'apollo'", {})]], size=14, color=TEXT, font=MONO)
text(s, 7.05, 4.05, 5.2, 0.3, "DELTA PUSHED BY TRIGGERWARE", size=11, color=DIM, bold=True)
text(s, 7.05, 4.45, 5.2, 0.9, [[("−  [\"MongoDB\"]", {"color": ROSE})], [("+  [\"PostgreSQL\"]", {"color": EMERALD})]],
     size=17, font=MONO, bold=True)
text(s, 0.9, 6.1, 11.5, 0.5, [[("Without TriggerWare: ", {"color": MUTED}),
                               ("a scraper and a diff job per source.   ", {"color": TEXT}),
                               ("With it: ", {"color": MUTED}), ("one connector.", {"color": EMERALD, "bold": True})]],
     size=17)
footer(s, 5)

# 6 ─ Labelled answers
s = slide("Because Drift knows where every fact came from, every line of an answer says how it knows. "
          "Verified means checked live through TriggerWare. Stale means a document still says something that's "
          "no longer true. Decision comes from a decision record, history is what used to be true, and inferred "
          "is Drift's best guess, never presented as fact. A plain AI search bot, given the same documents, "
          "just says MongoDB.")
eyebrow(s, "Answers you can trust")
title(s, "Every line says how it knows.")
text(s, 0.9, 2.2, 11.5, 0.4, "“Why did we move Apollo off MongoDB, who approved it, and what might break?”",
     size=17, color=MUTED)
rows = [
    ("VERIFIED", EMERALD, EMERALD_BG, "Apollo uses PostgreSQL  ·  checked live via TriggerWare"),
    ("STALE", AMBER, AMBER_BG, "“Apollo runbook” still says MongoDB"),
    ("DECISION", SKY, SKY_BG, "ADR-012: transactional joins  ·  approved by Priya Rao"),
    ("HISTORY", MUTED, ZINC_BG, "Apollo used MongoDB until Nov 4, 2026"),
    ("INFERRED", VIOLET, VIOLET_BG, "Payments, Notifications and Checkout may be affected"),
]
box(s, 0.9, 2.8, 7.9, 3.6)
for i, (lab, fg, bg, line) in enumerate(rows):
    y = 3.05 + i * 0.64
    pill(s, 1.2, y, lab, fg, bg, w=1.25, size=10)
    text(s, 2.7, y + 0.02, 5.9, 0.35, line, size=15, color=TEXT)
box(s, 9.1, 2.8, 3.35, 3.6, fill=ROSE_BG, line=ROSE, weight=0.75)
text(s, 9.4, 3.05, 2.8, 0.3, "A PLAIN AI SEARCH BOT", size=11, color=ROSE, bold=True)
text(s, 9.4, 3.5, 2.8, 1.2, "“Apollo uses MongoDB as its primary datastore.”", size=18, color=WHITE, bold=True)
text(s, 9.4, 4.95, 2.8, 1.2, "Same documents. Repeats the stale runbook, with confidence.", size=14, color=MUTED)
footer(s, 6)

# 7 ─ Demo
s = slide("Let's see it. I'll ask Drift a question, change one value in the live system, and watch what Drift does "
          "on its own.")
eyebrow(s, "Demo")
title(s, "One change in a live system.\nWatch what Drift does.", size=34)
demo = [
    ("Ask", "“What database does Apollo use?” → MongoDB, verified live."),
    ("Change", "An engineer updates the catalog: Apollo → PostgreSQL."),
    ("Detect", "TriggerWare pushes the delta. Drift alerts in seconds."),
    ("Explain", "Ask “why?”: stale runbook, decision, approver, blast radius."),
]
for i, (head, body) in enumerate(demo):
    y = 2.75 + i * 0.95
    text(s, 0.9, y, 0.5, 0.5, str(i + 1), size=24, color=EMERALD, bold=True)
    text(s, 1.45, y + 0.02, 4.3, 0.35, head, size=17, color=WHITE, bold=True)
    text(s, 1.45, y + 0.4, 4.4, 0.45, body, size=13, color=MUTED)
shot = HERE / "feed.png"
if shot.exists():
    frame = box(s, 6.25, 2.55, 6.2, 3.95, fill=CARD, line=BORDER, radius=0.03)
    pic = s.shapes.add_picture(str(shot), Inches(6.35), Inches(2.65), width=Inches(6.0))
    pic.crop_left, pic.crop_right, pic.crop_top, pic.crop_bottom = 0.27, 0.145, 0.08, 0.455
    pic.height = Emu(int(pic.width * (576 * (1 - 0.08 - 0.455)) / (1024 * (1 - 0.27 - 0.145))))
    frame.height = pic.height + Inches(0.2)
footer(s, 7)

# 8 ─ Close
s = slide("Wrong documentation doesn't announce itself; it waits for someone to trust it. Drift is a Company Brain "
          "that notices when it's wrong, and tells you before anyone gets hurt by it. Thank you.")
text(s, 0.9, 2.0, 11.5, 2.0, "Wrong documentation doesn’t announce itself.\nIt waits for someone to trust it.",
     size=40, color=WHITE, bold=True, spacing=1.1)
text(s, 0.9, 4.25, 11.5, 0.6, [[("Drift", {"bold": True, "color": EMERALD}),
                                ("  —  the Company Brain that notices when it is wrong.", {})]], size=24, color=TEXT)
text(s, 0.9, 5.55, 11.5, 0.9, [
    [("Live in the demo: ", {"bold": True, "color": MUTED}),
     ("change detection, memory updates with history, stale flags, dependency tracing, alerts.", {})],
    [("Synthetic: ", {"bold": True, "color": MUTED}),
     ("the demo company, its documents and catalog. “Check now” forces the poll so the change lands on cue.", {})],
], size=13, color=DIM)
footer(s, 8)

out = HERE / "Drift-intro.pptx"
prs.save(out)
print(out)
