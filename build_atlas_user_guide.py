"""Generate ATLAS_User_Guide.pdf — a friendly, non-technical user guide in the same format as the
engineering document. Screenshot placeholders ('SCREENSHOT N' + a description) mark where the user
will drop images in a second pass. Run:  .venv/Scripts/python.exe build_atlas_user_guide.py
"""
from __future__ import annotations

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (BaseDocTemplate, Frame, ListFlowable, ListItem, NextPageTemplate,
                                PageBreak, PageTemplate, Paragraph, Preformatted, Spacer, Table,
                                TableStyle)

OUT = r"C:\hackathonsandbox\ATLAS_User_Guide.pdf"
NAVY = colors.HexColor("#13243a")
ACCENT = colors.HexColor("#1f6f8b")
GREY = colors.HexColor("#6e7681")
LIGHT = colors.HexColor("#eef3f8")
SHOTBG = colors.HexColor("#f1f7fb")
RULE = colors.HexColor("#c7d3e0")
HEADER_TXT = "ATLAS   |   User Guide"
DATE_TXT = "June 2026"

ss = getSampleStyleSheet()
S = {
    "title": ParagraphStyle("title", parent=ss["Title"], fontName="Helvetica-Bold", fontSize=30,
                            textColor=NAVY, leading=34, spaceAfter=6, alignment=TA_CENTER),
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
    "code": ParagraphStyle("code", fontName="Courier", fontSize=8.4, textColor=colors.HexColor("#0b2030"),
                           leading=11.5, backColor=LIGHT, borderPadding=(6, 6, 6, 6)),
    "shotlbl": ParagraphStyle("shotlbl", fontName="Helvetica-Bold", fontSize=10.5, textColor=ACCENT,
                              leading=14, spaceAfter=2),
    "shotdesc": ParagraphStyle("shotdesc", fontName="Helvetica-Oblique", fontSize=9.5,
                               textColor=colors.HexColor("#33414f"), leading=13),
}

SHOTS = [0]   # running counter


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
    style = [("FONT", (0, 0), (-1, -1), "Helvetica", 8.8),
             ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#1c2733")),
             ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
             ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
             ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE), ("LINEAFTER", (0, 0), (-2, -1), 0.4, RULE),
             ("BOX", (0, 0), (-1, -1), 0.5, RULE)]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                  ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.8),
                  ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT])]
    t.setStyle(TableStyle(style))
    return [t, Spacer(1, 8)]


def code(text):
    return [Preformatted(text, S["code"]), Spacer(1, 8)]


def shot(desc):
    SHOTS[0] += 1
    n = SHOTS[0]
    cell = [Paragraph(f"SCREENSHOT {n}", S["shotlbl"]), Paragraph(desc, S["shotdesc"])]
    t = Table([[cell]], colWidths=[6.9 * inch], hAlign="LEFT")
    t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 1, ACCENT),
                           ("BACKGROUND", (0, 0), (-1, -1), SHOTBG),
                           ("TOPPADDING", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
                           ("LEFTPADDING", (0, 0), (-1, -1), 12), ("RIGHTPADDING", (0, 0), (-1, -1), 12)]))
    return [Spacer(1, 4), t, Spacer(1, 10)]


# ---- header / footer ----
def _decorate(canvas, doc, first=False):
    canvas.saveState()
    w, h = LETTER
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.5)
    canvas.line(0.8 * inch, 0.62 * inch, w - 0.8 * inch, 0.62 * inch)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(GREY)
    canvas.drawString(0.8 * inch, 0.45 * inch, "CONFIDENTIAL   |   SHI International Corp.")
    canvas.drawRightString(w - 0.8 * inch, 0.45 * inch, f"Page {canvas.getPageNumber()}")
    if not first:
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(ACCENT)
        canvas.drawString(0.8 * inch, h - 0.55 * inch, HEADER_TXT)
        canvas.drawRightString(w - 0.8 * inch, h - 0.55 * inch, DATE_TXT)
        canvas.setStrokeColor(RULE)
        canvas.line(0.8 * inch, h - 0.62 * inch, w - 0.8 * inch, h - 0.62 * inch)
    canvas.restoreState()


def _first(c, d):
    _decorate(c, d, True)


def _later(c, d):
    _decorate(c, d, False)


# ---- content model ----
SECTIONS = []


def sec(title, *blocks):
    flat = []
    for b in blocks:
        flat.extend(b if isinstance(b, list) else [b])
    SECTIONS.append((title, flat))


# 1
sec("Welcome to ATLAS",
    P("Welcome! This guide walks you through ATLAS from the ground up — no technical background needed. "
      "By the end you'll know what every screen does, what to click, and when to use it."),
    P("<b>What is ATLAS?</b> Think of ATLAS as a smart assistant for your customer work. You type what "
      "you want in plain English — \"write a trip report for yesterday's AWC meeting,\" \"is this product "
      "a good fit for ProPetro?\", \"who on our team knows application security?\" — and ATLAS does the "
      "work for you, in the background, while you keep going. It reads your meetings, builds reports and "
      "briefings, keeps a tidy profile of each customer, and even schedules tasks to run on their own."),
    P("<b>How does it think?</b> ATLAS runs on <b>your own Microsoft 365 Copilot</b>. When it needs to "
      "look something up or write something, it quietly drives Copilot in the background using <b>your</b> "
      "account — so everything stays inside your company's Microsoft world. There are no passwords to set "
      "up and nothing leaves your computer except the normal Copilot questions you'd ask anyway."),
    P("<b>The golden rule:</b> if you can describe it, you can ask ATLAS for it. The big box on the home "
      "screen is where you talk to it. Everything else in this guide is either a shortcut to common tasks "
      "or a place to review what ATLAS has produced."),
    shot("The ATLAS home screen exactly as it looks when the app first opens — the glowing orb in the "
         "center, the row of buttons above it, the 'Ask ATLAS to do anything' box, the calendar on the "
         "left, and Recent Artifacts on the right. A clean full-window capture."))

# 2
sec("Getting Started",
    h2("Opening ATLAS"),
    bullets(["Double-click <b>START.bat</b> (or the ATLAS icon if one was set up for you).",
             "A loading screen appears for a moment, then the home screen opens.",
             "That's it — there's nothing to install each time. Just open it and go."], numbered=True),
    h2("The one-time sign-in"),
    P("The very first time you ask ATLAS to do real work, a small Microsoft window may pop up asking you "
      "to <b>sign in to Microsoft 365</b>. Sign in with your normal work account — the same one you use "
      "for Outlook and Teams. ATLAS remembers it on your computer, so you usually only do this once."),
    P("If you ever see a browser window sitting open and waiting, it's just asking you to sign in. Log in "
      "and ATLAS picks right up where it left off."),
    shot("The Microsoft 365 sign-in window that appears on first use (the standard 'Pick an account' / "
         "sign-in page). Capture it as the user would see it pop up."),
    h2("A quick word on how work happens"),
    P("ATLAS does things in the background. When you ask for something, you'll see it appear in the "
      "<b>Working on</b> strip across the top of the home screen. You don't have to wait and watch — you "
      "can keep using ATLAS, and the finished result will be waiting for you when it's done."))

# 3
sec("The Home Screen — A Guided Tour",
    P("The home screen has three columns. Let's walk through each part so you know what everything is."),
    shot("The full home screen again, ideally with a simple numbered overlay (1 = top 'Working on' bar, "
         "2 = left Calendar, 3 = center orb + buttons + command box, 4 = right Recent Artifacts, 5 = the "
         "Today's Scheduled Jobs strip at the bottom). If overlaying numbers is hard, just a clean capture."),
    h2("Top of the screen — the menu and the 'Working on' bar"),
    bullets([
        "<b>Top-left</b> shows the ATLAS name. Along the top you'll find three simple menu links: "
        "<b>Home</b>, <b>Settings</b>, and <b>About</b>.",
        "<b>Working on</b> is the live status bar. Anything ATLAS is currently doing shows here with a "
        "little spinner; finished items show a check (or a warning if something went wrong). Click any "
        "item to see its details.",
    ]),
    shot("Close-up of the top bar: the ATLAS logo on the left, the Home / Settings / About links, and the "
         "'Working on' status bar with at least one active job (spinner) and one finished job (check mark). "
         "If possible, capture it while a task is running."),
    h2("Center — the orb and the command box (the heart of ATLAS)"),
    P("The glowing orb is ATLAS itself. Right below it is the big box that says <b>\"Ask ATLAS to do "
      "anything.\"</b> This is where you type your request in plain English and press Enter. The box is "
      "roomy — three lines tall — so you can write a longer request and still see all of it. (Tip: press "
      "<b>Shift+Enter</b> if you want to add a line break without sending yet.)"),
    P("Just above the orb is a row of five buttons that jump you straight to the main areas: "
      "<b>Customer Vault</b>, <b>People Resources</b>, <b>Cron Jobs</b>, <b>Skills</b>, and "
      "<b>Artifacts</b>. There's also a <b>Brainwave History</b> button to review ATLAS's thinking (more "
      "on that later)."),
    P("Below the command box you'll see <b>Continual Suggestions</b> — ATLAS's proactive ideas for what "
      "to do next (see its own chapter) — and, pinned at the very bottom, <b>Today's Scheduled Jobs</b>. "
      "The center column <b>scrolls</b> if there's a lot to show."),
    shot("Close-up of the center cluster: the five buttons in a row, the glowing orb beneath them, the "
         "'Brainwave History' button, the greeting line, and the large three-line 'Ask ATLAS to do "
         "anything' box with the send arrow. If you can, type an example like 'battlecard for ProPetro' "
         "into the box before capturing."),
    h2("Left — your Calendar"),
    P("The left column shows your meetings. Use the <b>Yesterday / Today / Tomorrow</b> buttons to switch "
      "days. Each meeting is a card you can click to see the details and prep. For a meeting that already "
      "happened, the detail view offers a one-click <b>Create Trip Report</b> button."),
    shot("The left Calendar column with 'Today' selected, showing a few meeting cards (title, time, a "
         "short preview)."),
    shot("A single meeting opened (after clicking its card), showing the meeting details and the "
         "'Create Trip Report' button for a past meeting."),
    h2("Right — Recent Artifacts"),
    P("Everything ATLAS produces — trip reports, briefings, battlecards, answers — is saved as an "
      "<b>artifact</b>. The right column lists your most recent ones, newest first. Click any to open and "
      "read it. <b>open all</b> takes you to the full Artifacts library."),
    shot("The right 'Recent Artifacts' column showing several recent items with their icons, names, and "
         "dates."),
    h2("Bottom — Today's Scheduled Jobs"),
    P("If you've set up any automatic tasks (see <b>Cron Jobs</b>), the ones due today appear in a small "
      "strip at the very bottom of the center, with their time and a check mark once they've run. It stays "
      "tucked away at the bottom so it never gets in your way."),
    shot("The 'Today's Scheduled Jobs' strip at the bottom of the home screen, showing one or two "
         "scheduled items with their times. (Set a cron job for today first so this appears.)"))

# 4
sec("Talking to ATLAS — The Command Box",
    P("The command box is the simplest and most powerful part of ATLAS. You don't need to learn special "
      "words — just say what you want. Here are real examples you can try:"),
    bullets([
        "<i>\"Write a trip report for yesterday's AWC meeting.\"</i>",
        "<i>\"Create a battlecard for ProPetro.\"</i>",
        "<i>\"Is Verkada a good fit for AWC?\"</i>",
        "<i>\"Trip reports for all my external customer meetings from May 21 to June 5.\"</i>",
        "<i>\"Who on our team is an expert in application security?\"</i>",
        "<i>\"What can you do?\"</i>  (ATLAS will list everything it can help with.)",
    ]),
    P("After you press Enter, ATLAS shows its thinking and routes your request to the right place. The "
      "finished result lands in <b>Artifacts</b>, and a record of how ATLAS handled it goes to "
      "<b>Brainwave History</b>. You can keep typing new requests — ATLAS handles several at once."),
    P("Don't worry about getting the wording perfect. If ATLAS isn't sure, it will make its best guess "
      "and tell you what it did; if it truly can't do something, it says so and suggests what would be "
      "needed. You really can't break it."))

sec("Continual Suggestions — ATLAS Reads the Room",
    P("ATLAS doesn't only wait for you to ask — it quietly looks ahead and suggests what you might want "
      "to do next, right on the Home screen, just above your scheduled jobs. Think of it as a sharp "
      "chief-of-staff who notices your next meeting is with a customer and asks, \"want me to prep you?\""),
    P("Each suggestion is a single tap. It only <b>suggests</b> — nothing runs until you click it, and "
      "then it runs just like any command you'd type. <b>Hover</b> over a suggestion to see exactly what "
      "it will do; click the <b>×</b> to dismiss one you don't want."),
    shot("The Home screen showing the Continual Suggestions panel — the 'Suggested next steps' header, "
         "a few suggestion chips, and the 'Suggest now' button — positioned just above the "
         "Today's-Scheduled-Jobs strip."),
    h2("Two kinds of suggestions"),
    bullets([
        "<b>Instant ideas</b> — based on your calendar and recent work (e.g. \"Prep me for the ProPetro "
        "meeting\", \"Strategic briefing for AWC\"). They appear immediately, for free.",
        "<b>Smart ideas</b> (marked <b>AI</b>) — ATLAS reads what you've filed on that customer and "
        "proposes specific plays: a battlecard against a competitor they mentioned, researching a "
        "product they're evaluating, and so on.",
    ]),
    h2("Get ideas any time"),
    P("The smart ideas refresh on their own (about once an hour, and whenever your next meeting changes). "
      "Want them right now? Click <b>Suggest now</b> — ATLAS thinks immediately and the new ideas pop in. "
      "Every batch it generates is also saved in <b>Brainwave History</b>, so you can look back at what it "
      "suggested and why."),
    shot("A suggestion being hovered so its tooltip shows the full, detailed description of what it will "
         "do (or a suggestion just after it was clicked, running on the 'Working on' bar)."),
    P("You control all of this in <b>Settings → Continual Advice</b>: turn it on or off, turn the smart "
      "(AI) ideas on or off, set how often they refresh, focus them on one specific customer, or keep "
      "them to work hours only."))

# 5  (the slightly technical one)
sec("The ATLAS Brain — Why It's More Than a Copilot Prompt",
    P("This is the one section where we'll get a little more technical — because it's the part that makes "
      "ATLAS special. When you type a request, ATLAS does <b>not</b> simply forward it to Copilot and hand "
      "you back the first reply. It runs a small reasoning process first, and often coordinates several "
      "Copilot sessions working in parallel."),
    h2("Step 1 - It decides what you're really asking for"),
    P("Every request first goes to the <b>Brain</b>, which classifies it: is this a single task, a job "
      "that should be split into several, a deep research question, a settings change, or something ATLAS "
      "can't do yet? It makes this decision by checking your request against its own list of abilities — "
      "so it answers honestly about what it can and can't do, instead of guessing."),
    h2("Step 2 - It breaks big jobs into many"),
    P("A single skill works on one thing at a time — one meeting, one customer. So when you ask for "
      "something that covers <b>many</b> targets, the Brain reasons about it and splits the job up. "
      "\"Battlecards for AWC, ProPetro and Sendero\" becomes three battlecards running side by side. "
      "\"Trip reports for all my meetings last week\" becomes one report per meeting. ATLAS even "
      "understands dates and time ranges, gathers your calendar in parallel chunks, filters to the "
      "meetings you care about, and then works through them a few at a time so your computer stays "
      "responsive."),
    h2("Step 3 - For big questions, it runs a team of agents (a 'Brainwave')"),
    P("When you ask an evaluation question like \"is this product a good fit for this customer?\", ATLAS "
      "launches a <b>Brainwave</b>: it opens several Copilot sessions at once, each with a different job, "
      "then combines their findings into one grounded answer."),
    table([["Agent", "What it studies"],
           ["Saved-data agent", "Everything you've already filed on that customer (their trip reports + "
            "technology profile) - the source of truth"],
           ["Research agent", "The product itself - how it works, competitors, pricing, where it fits"],
           ["Live-check agent", "Your live Microsoft 365 for anything recent that isn't in the filed notes"],
           ["Synthesis", "Merges all three into a single, grounded recommendation"]],
          [1.5, 5.0]),
    P("This is the difference between asking one person off the top of their head and sending a small "
      "research team to come back with a briefed answer."),
    h2("Step 4 - It shows its work (the Reasoning Receipt)"),
    P("Every request leaves a <b>Reasoning Receipt</b> in Brainwave History. The receipt shows what you "
      "asked, what the Brain decided and why, which agents it used (and which background Copilot sessions "
      "ran them), the rationale behind the answer, and the technology it used to get there. This lets you "
      "judge the quality of each result at a glance - you're never left wondering how ATLAS reached a "
      "conclusion."),
    shot("A finished Brainwave open in ATLAS, scrolled so the reader can see BOTH the written verdict AND "
         "the trace table that lists the agents, their mode (Work/Web), the Chrome instance, and the "
         "output - i.e. the 'how it was worked out' part. This is the money shot for this section."),
    P("<b>The takeaway:</b> ATLAS plans, divides work, runs parallel agents, grounds itself in your own "
      "filed data, and explains itself. That's why it can take on real multi-step work, not just answer a "
      "single question."))

# 6
sec("Skills - The Ready-Made Tasks",
    P("A <b>skill</b> is a ready-made task ATLAS knows how to do. You can let the command box pick the "
      "right skill for you, or open the <b>Skills</b> screen and run one directly by filling in a short "
      "form. Here's the full menu:"),
    table([["Skill", "What it does for you"],
           ["Trip Report", "Turns a meeting's transcript into a clean, structured recap"],
           ["Meeting Prep", "Briefs you before a meeting - context, agenda, your role"],
           ["Battlecard", "A competitive cheat-sheet for an account"],
           ["Strategic Briefing", "An executive-level briefing on an account"],
           ["Account 360", "A complete overview of a customer"],
           ["Follow-Up", "Drafts a follow-up plan or email after a meeting"],
           ["Whitespace", "Finds expansion and upsell opportunities in an account"],
           ["Environment Topology", "Maps out a customer's technology environment"],
           ["People Resources", "Finds the right SHI engineer or vendor for a need"],
           ["Daily Briefing", "Today's meetings with prep for each"],
           ["Knowledge Drop", "A curated knowledge digest"],
           ["Ask", "A general question-and-answer chat you can continue later"]],
          [1.7, 5.1]),
    shot("The Skills screen showing the grid of skill cards (each with its icon and a short description)."),
    P("To run one directly: click its card, fill in the box(es) it asks for (usually a customer or "
      "meeting name), and press the run button. The result appears in Artifacts when it's ready."),
    shot("A single skill opened into its input form - for example the Trip Report skill with a meeting "
         "name typed in, ready to run."),
    shot("A finished deliverable open and readable in ATLAS - for example a completed Trip Report - so the "
         "reader sees what a polished result looks like."))

# 7
sec("Customer Vault - Your Memory for Every Account",
    P("The <b>Customer Vault</b> is where ATLAS keeps a tidy, growing record of each customer. Everything "
      "you file here makes ATLAS smarter about that account over time."),
    shot("The Customer Vault screen: the searchable grid of customer cards, plus the button to create a "
         "new customer."),
    h2("Inside a customer"),
    P("Click a customer to open their page. You'll find:"),
    bullets([
        "<b>Overview &amp; Key Contacts</b> - a plain-English summary of the account and the important people.",
        "<b>Trip Reports</b> - every report you've filed for them.",
        "<b>Technology Profile (ATP)</b> - a structured picture of the technologies they use.",
        "<b>Network Diagrams &amp; Artifacts</b> - any diagrams and other deliverables filed to them.",
        "<b>Generations</b> - dated snapshots of the technology profile, so you can look back at earlier versions.",
    ]),
    shot("A customer's page showing the Overview and Key Contacts panel at the top and the tabs/sections "
         "(Trip Reports, ATP, Diagrams, Artifacts) below."),
    h2("Building and editing the technology profile"),
    P("Click <b>Generate from trip reports</b> and ATLAS reads everything you've filed for that customer "
      "and builds a technology profile automatically. You can fine-tune it in the <b>Edit Technology "
      "Profile</b> editor - add, change, or remove technologies - and your hand edits are always kept, "
      "even when you regenerate."),
    P("The <b>Topology</b> view turns that profile into a glowing, interactive map of the customer's "
      "environment, color-coded by status, where each technology also shows how many of your trip reports "
      "mention it and when it was last discussed."),
    shot("The Technology Topology view - the dark, glowing category-and-vendor map for a customer."),
    shot("The Edit Technology Profile editor, showing the list of technologies with the add/edit/delete "
         "controls."),
    P("<b>Deleting a customer</b> is safe: it asks you to confirm and enter your 6-digit System PIN, then "
      "moves everything to a recycle bin rather than truly deleting it."))

# 8
sec("Artifacts - Everything ATLAS Has Made",
    P("Every report, briefing, battlecard, diagram, and answer ATLAS produces is saved as an "
      "<b>artifact</b>. The Artifacts library is where you find and manage them all."),
    bullets([
        "<b>Search</b> - type any word to find an artifact by its title, customer, or contents.",
        "<b>Unfiled only</b> - a toggle that shows just the artifacts not yet assigned to a customer, so "
        "you can quickly file them.",
        "<b>Open &amp; read</b> - click any artifact to read it in a clean view.",
        "<b>File to a customer</b> - assign (or move) an artifact to a customer's vault.",
        "<b>Email</b> - for trip reports, open a ready-to-send Outlook draft.",
        "<b>Delete</b> - safely remove an artifact (PIN-protected; it goes to the recycle bin).",
    ]),
    shot("The Artifacts library screen, showing the search box, the 'Unfiled only' toggle, and a list of "
         "artifacts."),
    P("Trip reports you already had as files are pulled in automatically, so your whole history is "
      "searchable and readable in one place - and any artifact can be moved between customers whenever you like."))

# 9
sec("People Resources - Find the Right Expert",
    P("<b>People Resources</b> is a searchable directory of engineers, vendors, assessments, and tools. "
      "When you need the right person or partner for an engagement, this is the fastest way to find them."),
    bullets([
        "<b>Ask in plain English</b> - type something like \"a TOLA expert who can do PAM or EDR\" in the "
        "command box and ATLAS returns the best matches, with a short rationale for why they fit.",
        "<b>Or browse</b> - open the People Resources screen, use the category chips and the filter box to "
        "narrow by name, specialty, or region.",
        "<b>Keep it current</b> - you can add, edit, or remove entries (protected by your System PIN), or "
        "<b>Import</b> a new spreadsheet/CSV; the previous version is safely archived, never lost.",
    ]),
    shot("The People Resources screen with the category chips along the top and the filter box, showing a "
         "filtered list of people (e.g. after typing 'EDR' or 'TOLA')."))

# 10
sec("Cron Jobs - Let ATLAS Work on a Schedule",
    P("<b>Cron Jobs</b> let ATLAS do things automatically on a schedule, even when you're not watching. A "
      "cron job is just an instruction plus a time."),
    h2("Creating a scheduled job"),
    bullets([
        "Type the instruction in plain English - the same way you'd type it in the command box "
        "(e.g. \"create trip reports for all of today's external customer meetings\").",
        "Pick a <b>time</b>.",
        "Choose how often: <b>Daily</b>, <b>Weekly</b> (then tick the weekdays), or <b>Monthly</b> "
        "(then pick the day of the month).",
        "Save. ATLAS shows the schedule in plain language and when it will next run.",
    ], numbered=True),
    shot("The Cron Jobs create form: the instruction box, the time picker, and the Daily/Weekly/Monthly "
         "choice with the weekday checkboxes visible."),
    P("When a job is due, ATLAS runs the instruction through its Brain exactly as if you'd typed it - so a "
      "scheduled job gets the full power of planning and multi-step work, not a watered-down version. "
      "Jobs run while ATLAS is open, in the timezone you set in Settings."),
    P("Your saved jobs are listed with their schedule and next run time, and each can be turned on or off "
      "or deleted. The ones due today also appear at the bottom of the home screen."),
    shot("The Cron Jobs list showing one or more saved jobs with their plain-language schedule, next-run "
         "time, and the enable/disable and delete controls."))

# 11
sec("Brainwave History - A Record of Every Interaction",
    P("Every time you ask ATLAS something, it saves a <b>Reasoning Receipt</b> here. This is your audit "
      "trail and your quality check - open any entry to see exactly what ATLAS did and why."),
    shot("The Brainwave History screen: the list of past interactions, each with its title, date, and a "
         "short preview."),
    P("Open one and you'll see the full receipt: what you asked, what the Brain decided and why, the "
      "agents and background sessions it used, the rationale for the answer, and the technology it used. "
      "Deep research Brainwaves also include the full agent trace and the final recommendation."),
    shot("A single Reasoning Receipt opened, showing the 'Brain logic', the agent/technology trace, and "
         "the rationale sections."))

# 12
sec("Settings - Make ATLAS Yours",
    P("The <b>Settings</b> page (top menu) holds a handful of simple preferences. Change what you like and "
      "click <b>Save</b>."),
    table([["Setting", "What it controls"],
           ["Trip report recipients", "The email addresses the Email button fills in for you"],
           ["Email signature", "A signature added under the report in the draft"],
           ["Auto-open Outlook draft", "Automatically open a draft when a trip report finishes"],
           ["Show the Copilot Chrome windows", "Off by default (ATLAS works invisibly). Turn on to watch "
            "the background Copilot windows - handy if you're curious or troubleshooting"],
           ["Timezone", "The timezone your scheduled Cron Jobs run in"],
           ["System PIN", "A 6-digit PIN required before anything can be deleted - your safety lock"],
           ["Continual Advice", "Turn Continual Suggestions on/off; turn the smart (AI) ideas on/off; "
            "how often they refresh; focus them on one customer; keep them to work hours"],
           ["Brain Rules", "Plain-English rules that guide how the Brain works (advanced, optional)"]],
          [2.1, 4.7]),
    shot("The Settings screen showing the fields above - recipients, signature, the checkboxes, timezone, "
         "the System PIN field, and the Brain Rules box."),
    P("<b>About the System PIN:</b> set this early. Nothing in ATLAS is ever truly deleted without it, and "
      "even then, deleted items go to a recycle bin rather than vanishing - so you can always recover."))

# 13
sec("Tips, Good Habits & Troubleshooting",
    h2("Get the most out of ATLAS"),
    bullets([
        "<b>File your trip reports to customers.</b> The more you file, the smarter ATLAS gets about each "
        "account - its profiles and recommendations are built from what you've filed.",
        "<b>Use plain language.</b> You don't need keywords. Describe the outcome you want.",
        "<b>Let it run.</b> Kick off several requests and come back - work continues in the background and "
        "survives even if you close and reopen ATLAS.",
        "<b>Check the receipt.</b> If a result surprises you, open its Reasoning Receipt to see how ATLAS "
        "got there.",
        "<b>Set your PIN and timezone first.</b> Two minutes in Settings saves headaches later.",
    ]),
    h2("Common questions"),
    table([["If you see...", "What to do"],
           ["A browser window sitting open", "It wants you to sign in to Microsoft 365. Log in and the "
            "task continues automatically."],
           ["Nothing seems to happen", "Give it a few seconds and watch the 'Working on' bar - work runs "
            "in the background."],
           ["It asks for a PIN", "That's the delete safety lock. Enter your 6-digit System PIN (set it in "
            "Settings if you haven't)."],
           ["A result looks off", "Open its Reasoning Receipt in Brainwave History to see the logic, and "
            "try rephrasing your request."],
           ["You deleted something by mistake", "Nothing is truly gone - deleted items move to a recycle "
            "bin and can be recovered."]],
          [2.3, 4.5]),
    P("That's everything. ATLAS is built to be forgiving and easy - when in doubt, just type what you want "
      "into the box and let it do the work."))


# ---- build ----
def build():
    doc = BaseDocTemplate(OUT, pagesize=LETTER, leftMargin=0.8 * inch, rightMargin=0.8 * inch,
                          topMargin=0.85 * inch, bottomMargin=0.8 * inch,
                          title="ATLAS - User Guide", author="Manuel Zelaya")
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="main")
    doc.addPageTemplates([PageTemplate(id="first", frames=[frame], onPage=_first),
                          PageTemplate(id="later", frames=[frame], onPage=_later)])

    story = []
    story += [Spacer(1, 1.7 * inch),
              Paragraph("A.T.L.A.S.", S["title"]),
              Paragraph("User Guide", S["subtitle"]),
              Spacer(1, 8),
              Paragraph("Autonomous Tactical Learning Agentic System", S["tpb"]),
              Spacer(1, 6),
              Paragraph("A friendly, step-by-step guide to using ATLAS - no technical background needed", S["tag"]),
              Spacer(1, 1.5 * inch),
              Paragraph("Manuel Zelaya", S["tpb"]),
              Paragraph("Solutions Architect", S["tp"]),
              Spacer(1, 6),
              Paragraph("Version 1.0  |  June 2026", S["tp"]),
              Paragraph("SHI International Corp.  |  Solutions Engineering", S["tp"]),
              Spacer(1, 24),
              Paragraph("CONFIDENTIAL", S["tpb"]),
              NextPageTemplate("later"), PageBreak()]

    story.append(Paragraph("TABLE OF CONTENTS", S["h1"]))
    for i, (t, _) in enumerate(SECTIONS, 1):
        story.append(Paragraph(f"{i}&nbsp;&nbsp;&nbsp;{t}", S["toc"]))
    story.append(Spacer(1, 14))
    story.append(Paragraph("&nbsp;", S["body"]))
    story.append(Paragraph("<i>This guide contains numbered SCREENSHOT placeholders. Capture each one as "
                           "described, then they'll be inserted in the next version.</i>", S["tag"]))
    story.append(PageBreak())

    for i, (t, blocks) in enumerate(SECTIONS, 1):
        story.append(Paragraph(f"{i}.&nbsp;&nbsp;{t}", S["h1"]))
        story += blocks
        story.append(Spacer(1, 4))

    doc.build(story)
    print("wrote", OUT, "| screenshots:", SHOTS[0])


if __name__ == "__main__":
    build()
