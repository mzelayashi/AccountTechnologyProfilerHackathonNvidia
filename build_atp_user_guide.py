"""Generate ATP_User_Guide.pdf — the end-user guide for ATP (Account Technology Profiler).
Run:  .venv/bin/python build_atp_user_guide.py
"""
from __future__ import annotations

import os

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (BaseDocTemplate, Frame, ListFlowable, ListItem, NextPageTemplate,
                                PageBreak, PageTemplate, Paragraph, Preformatted, Spacer, Table,
                                TableStyle)

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ATP_User_Guide.pdf")
NAVY = colors.HexColor("#13243a")
ACCENT = colors.HexColor("#1f6f8b")
GREY = colors.HexColor("#6e7681")
LIGHT = colors.HexColor("#eef3f8")
RULE = colors.HexColor("#c7d3e0")
HEADER_TXT = "ATP   |   User Guide"
DATE_TXT = "June 2026"

ss = getSampleStyleSheet()
S = {
    "title": ParagraphStyle("title", parent=ss["Title"], fontName="Helvetica-Bold", fontSize=32,
                             textColor=NAVY, leading=36, spaceAfter=6, alignment=TA_CENTER),
    "subtitle": ParagraphStyle("subtitle", fontName="Helvetica", fontSize=14, textColor=ACCENT,
                               leading=18, alignment=TA_CENTER, spaceAfter=4),
    "tag": ParagraphStyle("tag", fontName="Helvetica", fontSize=10.5, textColor=GREY,
                          alignment=TA_CENTER, leading=15),
    "tp": ParagraphStyle("tp", fontName="Helvetica", fontSize=11, textColor=colors.black,
                         alignment=TA_CENTER, leading=16),
    "tpb": ParagraphStyle("tpb", fontName="Helvetica-Bold", fontSize=11, textColor=NAVY,
                          alignment=TA_CENTER, leading=16),
    "h1": ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=15, textColor=colors.white,
                         backColor=NAVY, leading=20, spaceBefore=16, spaceAfter=10,
                         leftIndent=6, rightIndent=6, borderPadding=(6, 6, 6, 6)),
    "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=11.5, textColor=ACCENT,
                         leading=15, spaceBefore=10, spaceAfter=4),
    "body": ParagraphStyle("body", fontName="Helvetica", fontSize=10, textColor=colors.HexColor("#1c2733"),
                           leading=14.5, spaceAfter=6, alignment=TA_LEFT),
    "bullet": ParagraphStyle("bullet", fontName="Helvetica", fontSize=10, textColor=colors.HexColor("#1c2733"),
                             leading=14),
    "toc": ParagraphStyle("toc", fontName="Helvetica", fontSize=10.5, textColor=NAVY, leading=18),
    "code": ParagraphStyle("code", fontName="Courier", fontSize=8.6, textColor=colors.HexColor("#0b2030"),
                           leading=11.5, backColor=LIGHT, borderPadding=(6, 6, 6, 6)),
}


def P(t):
    return Paragraph(t, S["body"])


def h2(t):
    return Paragraph(t, S["h2"])


def bullets(items, numbered=False):
    return ListFlowable([ListItem(Paragraph(i, S["bullet"]), leftIndent=14) for i in items],
                        bulletType="1" if numbered else "bullet", start="1" if numbered else None,
                        bulletFormat="%s." if numbered else None,
                        bulletFontName="Helvetica", bulletFontSize=9, leftIndent=12, spaceAfter=6,
                        bulletColor=NAVY if numbered else ACCENT)


def table(rows, widths, header=True):
    t = Table(rows, colWidths=[w * inch for w in widths], hAlign="LEFT")
    style = [
        ("FONT", (0, 0), (-1, -1), "Helvetica", 9),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#1c2733")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
        ("BOX", (0, 0), (-1, -1), 0.5, RULE),
    ]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                  ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
                  ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT])]
    t.setStyle(TableStyle(style))
    return [t, Spacer(1, 8)]


def code(text):
    return [Preformatted(text, S["code"]), Spacer(1, 8)]


def _decorate(canvas, doc, first=False):
    canvas.saveState()
    w, h = LETTER
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.5)
    canvas.line(0.8 * inch, 0.62 * inch, w - 0.8 * inch, 0.62 * inch)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(GREY)
    canvas.drawString(0.8 * inch, 0.45 * inch, "SHI International Corp.")
    canvas.drawRightString(w - 0.8 * inch, 0.45 * inch, f"Page {canvas.getPageNumber()}")
    if not first:
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(ACCENT)
        canvas.drawString(0.8 * inch, h - 0.55 * inch, HEADER_TXT)
        canvas.drawRightString(w - 0.8 * inch, h - 0.55 * inch, DATE_TXT)
        canvas.setStrokeColor(RULE)
        canvas.line(0.8 * inch, h - 0.62 * inch, w - 0.8 * inch, h - 0.62 * inch)
    canvas.restoreState()


def _first(canvas, doc):
    _decorate(canvas, doc, first=True)


def _later(canvas, doc):
    _decorate(canvas, doc, first=False)


SECTIONS = []


def sec(title, *blocks):
    flat = []
    for b in blocks:
        flat.extend(b if isinstance(b, list) else [b])
    SECTIONS.append((title, flat))


# 1
sec("WELCOME TO ATP",
    P("<b>ATP — the Account Technology Profiler</b> — is your AI assistant for running your accounts. "
      "You type what you want in one command box and ATP figures out what to do: answer questions about "
      "your customers, research a technology on the web, judge whether a product fits an account, build "
      "briefings, or draw network and vision diagrams."),
    P("Everything runs on a <b>local NVIDIA Nemotron model on two H100 GPUs</b> in your own environment — "
      "<b>no cloud AI service, no API keys, and your customer data never leaves the machine</b> (the one "
      "exception is the web-research feature, which searches the public web when you ask it to)."),
    P("This guide walks through everything ATP can do and how to use it."))

# 2
sec("STARTING UP & THE PRE-DEMO CHECK",
    P("Open the <b>Account Technology Profiler</b> shortcut on the desktop to launch the app window. To "
      "confirm the AI model is live before a demo, run the health check in a terminal:"),
    code("./demo_health.sh"),
    P("It prints a green board: both H100 GPUs, the Nemotron model loaded across them, the inference "
      "engine, a live test generation (with speed), and the app. If something is down, run:"),
    code("./demo_health.sh --recover     # restarts the model only if it's actually down"),
    bullets([
        "All green → you're ready to demo.",
        "Red items → the recovery line above fixes the model; the board also lists the exact commands.",
    ]))

# 3
sec("THE HOME SCREEN & COMMAND BOX",
    P("The Home screen centers on the <b>command box</b> — type anything and press Enter. Underneath are "
      "two starter chips you can click to pre-fill a request:"),
    bullets([
        "<b>🎯 Create a strategic account briefing for a customer</b>",
        "<b>🧠 Research whether a new technology fits a customer's infrastructure</b>",
    ]),
    P("Click a chip and the first <font face='Courier'>[bracketed]</font> part is selected — just type the "
      "customer or technology over it and press Enter. Around the box you'll also find your live tasks "
      "(<b>Working on</b>, with an ✕ to cancel), <b>Recent Artifacts</b>, and buttons for the Customer "
      "Vault, Skills, Cron Jobs, Brainwave History, and Artifacts."),
    P("Whatever you type is understood and routed automatically — you don't pick a mode. Examples:"),
    table([["Type this…", "ATP does…"],
           ["which customers use Palo Alto firewalls?", "Searches every customer and answers with citations"],
           ["does Aspen Health use CrowdStrike?", "Checks that one customer; shows where it found it"],
           ["research the latest Palo Alto firewalls", "Searches the web and writes a sourced brief"],
           ["is Verkada a good fit for Aspen Health?", "Runs a multi-agent analysis + a verdict"],
           ["strategic briefing for Aspen Health", "Builds a full strategic briefing"]],
          [2.9, 4.0]))

# 4
sec("ASKING ABOUT YOUR CUSTOMERS (RAG)",
    P("Ask a plain question about your accounts and ATP searches the Customer Vault — trip reports, the "
      "technology profile, vision/network diagrams, and filed artifacts — then answers with <b>citations</b> "
      "to exactly where each fact came from."),
    bullets([
        "<b>Across all customers:</b> “which of my customers use CrowdStrike?” → a list, each with where it was found.",
        "<b>One customer:</b> “does Aspen Health use Palo Alto?” → yes/no with the specific trip reports / profile entries.",
        "If nothing matches, ATP says so plainly rather than guessing.",
    ]))

# 5
sec("RESEARCHING A TECHNOLOGY (WEB)",
    P("Ask ATP to <b>research</b> something and it goes to the web (not your vault): “research the latest "
      "Palo Alto firewalls”, “what's new with Zscaler”. A 🌐 research task runs, then a sourced brief "
      "appears as an artifact and a Brainwave-History entry so you can see the reasoning."),
    P("This is the only feature that reaches the internet, and only the search words leave the machine. "
      "You can block specific sources (see Guardrails)."))

# 6
sec("“IS IT A GOOD FIT?” — BRAINWAVES",
    P("Ask whether a product fits a customer — “is Verkada a good fit for Aspen Health?” — and ATP runs a "
      "<b>multi-agent Brainwave</b>:"),
    bullets([
        "🔎 one agent researches the product on the web, while 🗂 another studies that customer's saved infrastructure — <b>at the same time</b>;",
        "🧬 a third agent merges both into a grounded verdict (fit, where it fits, risks, recommended next step);",
        "🔎 a fourth agent <b>fact-checks the verdict</b> against the evidence and flags anything unsupported.",
    ]),
    P("The result lands in <b>Brainwave History</b> as a full receipt: what it decided and why, which "
      "agents ran (and that they ran in parallel on the Nemotron model), the verdict, and the self-check. "
      "This is where you go to see the logic behind any answer."))

# 7
sec("BRIEFINGS & OTHER SKILLS",
    P("Type “strategic briefing for &lt;customer&gt;” (or use the chip) and ATP builds a full briefing — "
      "executive summary, initiatives, opportunities, risks, talking points, and a decision-tree diagram — "
      "grounded in that customer's saved data. Other Brain skills (account snapshot, battlecard, "
      "whitespace, follow-up, environment topology) run the same way from the command box. The deliverable "
      "is saved to Artifacts and can be filed to the customer."))

# 8
sec("SEDRAW — NETWORK DIAGRAMS",
    P("Open <b>Skills → SEdraw Network Diagrams</b> and pick a customer. You can:"),
    bullets([
        "<b>Generate</b> a network map from an Excel intake already in that customer's folder;",
        "<b>＋ Create New</b> — start from a blank template and fill it in the built-in editor;",
        "<b>Edit</b> an existing intake in the GUI editor, then regenerate;",
        "<b>🗑 Delete</b> a diagram (PIN-guarded — see Deleting Things).",
    ]),
    P("The generated diagram opens right in the window; a download button gives you the .drawio file."))

# 9
sec("SEDRAW — CONVERT FROM A WORD DOC",
    P("In the same Network view, click <b>📄 Convert from DOCX</b> and pick a Word intake (.docx). The "
      "Nemotron model reads the document — paragraphs and tables — and does its best to map it onto the "
      "network intake form, then generates the map automatically."),
    bullets([
        "It maps what it reasonably can (sites, firewalls, switches, servers, storage, connectivity) and skips anything that doesn't fit — it won't invent devices.",
        "The mapped intake is saved as an editable spreadsheet, so you can open the editor, fix anything, and regenerate.",
        "It runs in the background (you'll see progress); large documents are summarized to fit the model.",
    ]))

# 10
sec("SEDRAW — VISION BOARDS",
    P("Open <b>Skills → SEdraw Vision Boards</b> and pick a customer (the Vision Studio opens). Describe "
      "the environment in plain English in two boxes — <b>Current State</b> and <b>Future State</b> — and "
      "click Generate. Nemotron builds one combined architecture diagram (current on top, future below)."),
    bullets([
        "It runs as a background task; the diagram appears and is filed as an artifact.",
        "<b>History</b> lists earlier boards — open or edit any of them in the full editor.",
        "<b>🗑 Delete</b> a board (PIN-guarded).",
    ]))

# 11
sec("THE CUSTOMER VAULT & PROFILES",
    P("<b>Customer Vault</b> lists every account. Open one to see its trip reports, its <b>Account "
      "Technology Profile</b> (technologies, overview, key contacts, topology), network/vision diagrams, "
      "and artifacts."),
    bullets([
        "<b>✨ Generate</b> rebuilds the technology profile from the customer's trip reports; each run is saved as a dated <b>generation</b> snapshot you can compare over time.",
        "Your hand-edits are preserved across regenerations (the system merges rather than overwrites).",
        "<b>🛰 Topology</b> shows the rendered network/technology diagram; older generations each have a 🗑 to remove (the live ‘Current’ profile is protected).",
    ]))

# 12
sec("ARTIFACTS & BRAINWAVE HISTORY",
    bullets([
        "<b>Artifacts</b> — every deliverable ATP produces (briefings, diagrams, research briefs, profiles). Search by title/customer/content, open them in-app, and file them to a customer.",
        "<b>Brainwave History</b> — a reasoning receipt for every command: what ATP decided and why, which agents ran (on the Nemotron model), the rationale, and (for brainwaves) the verdict + self-check. This is your audit trail of the AI's thinking.",
    ]))

# 13
sec("DELETING THINGS SAFELY",
    P("Every delete in ATP — a customer, an artifact, a vision board, a network diagram, or a profile "
      "generation — is a <b>soft delete</b>. Clicking 🗑 asks for your <b>6-digit System PIN</b>; the item "
      "then moves to a recycle bin and disappears from the app, but is <b>never erased</b> — it can be "
      "restored from <font face='Courier'>vault/recyclebin/</font>."),
    bullets([
        "Set your PIN in <b>Settings</b> first; without it, deletion is blocked (a safety guard).",
        "This is the same safe-delete behavior everywhere in the app.",
    ]))

# 14
sec("GUARDRAILS — KEEPING ATP ON-TASK",
    P("ATP can run a <b>guardrail</b> on the command box that keeps it on-topic (your customers + "
      "technology research) and politely declines off-topic, unsafe, or prompt-injection requests. It is "
      "<b>off by default</b> and <b>fail-open</b> (it never blocks legitimate work if something goes wrong)."),
    h2("Turning it on"),
    bullets([
        "Quick terminal toggle: <font face='Courier'>./guardrails.sh on</font> (or off / status).",
        "Or use the <b>Guardrails Control Panel</b> desktop shortcut (opens at http://localhost:8090) — a separate window that can't affect the main app.",
    ]),
    h2("What you can control (the levers)"),
    bullets([
        "Master on/off · keep on-topic · block unsafe · block prompt-injection · strictness (lenient / balanced / strict).",
        "<b>Blocked words</b> — refuse any command containing them (e.g. “reddit”).",
        "<b>Blocked research sources</b> — stop the web-research agent from using certain domains (e.g. reddit.com).",
        "<b>Live Test box</b> — type a phrase to see ALLOW or REFUSE with the reason, before you enable it.",
        "<b>Recent blocks</b> — a live log of what got declined. Click <b>💾 Save</b> to confirm changes (they take effect on your next command — no restart).",
    ]))

# 15
sec("SETTINGS",
    bullets([
        "<b>System PIN</b> — required to delete anything.",
        "<b>Timezone</b> — used by scheduled jobs.",
        "<b>Guardrails</b> — enable/disable the command-box rail.",
        "<b>Brain Rules</b> — guidance injected into the assistant's prompts (rule #1: look at the customer's saved data first).",
    ]))

# 16
sec("TIPS & RECOVERY",
    table([["If…", "Do this"],
           ["You want to prove the model is live", "./demo_health.sh — shows the 2× H100s, the model, and a live generation."],
           ["The model seems down mid-demo", "./demo_health.sh --recover (heals the model only if it's actually down)."],
           ["A task is taking too long", "Click the ✕ on its chip in ‘Working on’ — it stops the task and any sub-agents."],
           ["The guardrail blocked something you wanted", "Lower strictness / clear blocked words in the panel, or ./guardrails.sh off."],
           ["A Word→network convert looks thin", "Open the generated intake in the editor, fix it, and regenerate."],
           ["You deleted something by mistake", "It's in vault/recyclebin/ — nothing is ever hard-deleted."]],
          [2.6, 4.6]))


def build():
    doc = BaseDocTemplate(OUT, pagesize=LETTER,
                          leftMargin=0.8 * inch, rightMargin=0.8 * inch,
                          topMargin=0.85 * inch, bottomMargin=0.8 * inch,
                          title="ATP — User Guide", author="Manuel Zelaya")
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="main")
    doc.addPageTemplates([
        PageTemplate(id="first", frames=[frame], onPage=_first),
        PageTemplate(id="later", frames=[frame], onPage=_later),
    ])

    story = []
    story += [Spacer(1, 1.8 * inch),
              Paragraph("ATP", S["title"]),
              Paragraph("Account Technology Profiler", S["subtitle"]),
              Spacer(1, 8),
              Paragraph("User Guide", S["tpb"]),
              Spacer(1, 6),
              Paragraph("Your AI assistant for running your accounts — powered by a local NVIDIA model", S["tag"]),
              Paragraph("Nemotron-Super-49B on 2× H100  |  private &amp; local  |  no API keys", S["tag"]),
              Spacer(1, 1.5 * inch),
              Paragraph("SHI International Corp.  |  Solutions Engineering", S["tp"]),
              Paragraph("Version 2.0  |  June 2026", S["tp"]),
              NextPageTemplate("later"), PageBreak()]

    def _toc_label(t):
        lbl = t.title()
        for a, b in (("Atp", "ATP"), ("Sedraw", "SEdraw"), ("Docx", "DOCX"), ("Rag", "RAG"),
                     ("Word Doc", "Word Doc"), (" & ", " &amp; ")):
            lbl = lbl.replace(a, b)
        return lbl

    story.append(Paragraph("CONTENTS", S["h1"]))
    for i, (t, _) in enumerate(SECTIONS, 1):
        story.append(Paragraph(f"{i}&nbsp;&nbsp;&nbsp;{_toc_label(t)}", S["toc"]))
    story.append(PageBreak())

    for i, (t, blocks) in enumerate(SECTIONS, 1):
        story.append(Paragraph(f"{i}.&nbsp;&nbsp;{t}", S["h1"]))
        story += blocks
        story.append(Spacer(1, 4))

    doc.build(story)
    print("wrote", OUT)


if __name__ == "__main__":
    build()
