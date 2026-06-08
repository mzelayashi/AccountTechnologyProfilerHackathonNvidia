"""Generate SHI_ATLAS_Engineering_Documentation.pdf — same format/style as the ATP profiler doc.

Title page + running header/footer ("CONFIDENTIAL | SHI International Corp.   Page N"), a numbered TOC,
UPPERCASE numbered section headers, title-case subsections, tables, bullet/numbered lists, code blocks,
and a file map. Run:  .venv/Scripts/python.exe build_atlas_engineering_doc.py
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

OUT = r"C:\hackathonsandbox\SHI_ATLAS_Engineering_Documentation.pdf"
NAVY = colors.HexColor("#13243a")
ACCENT = colors.HexColor("#1f6f8b")
TEAL = colors.HexColor("#2aa0a4")
GREY = colors.HexColor("#6e7681")
LIGHT = colors.HexColor("#eef3f8")
RULE = colors.HexColor("#c7d3e0")
HEADER_TXT = "ATLAS   |   Engineering Documentation"
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
    "body": ParagraphStyle("body", fontName="Helvetica", fontSize=9.7, textColor=colors.HexColor("#1c2733"),
                           leading=14, spaceAfter=6, alignment=TA_LEFT),
    "bullet": ParagraphStyle("bullet", fontName="Helvetica", fontSize=9.7, textColor=colors.HexColor("#1c2733"),
                             leading=13.5),
    "toc": ParagraphStyle("toc", fontName="Helvetica", fontSize=10.5, textColor=NAVY, leading=18),
    "code": ParagraphStyle("code", fontName="Courier", fontSize=8.3, textColor=colors.HexColor("#0b2030"),
                           leading=11, backColor=LIGHT, borderPadding=(6, 6, 6, 6)),
    "cap": ParagraphStyle("cap", fontName="Helvetica-Oblique", fontSize=8.5, textColor=GREY, leading=12,
                          spaceAfter=8),
}


def P(t):
    return Paragraph(t, S["body"])


def bullets(items, numbered=False):
    sty = S["bullet"]
    lf = ListFlowable([ListItem(Paragraph(i, sty), leftIndent=14) for i in items],
                      bulletType="1" if numbered else "bullet", start="1" if numbered else None,
                      bulletFormat="%s." if numbered else None,
                      bulletFontName="Helvetica", bulletFontSize=9, leftIndent=12, spaceAfter=6,
                      bulletColor=NAVY if numbered else ACCENT)
    return lf


def table(rows, widths, header=True):
    t = Table(rows, colWidths=[w * inch for w in widths], hAlign="LEFT")
    style = [
        ("FONT", (0, 0), (-1, -1), "Helvetica", 8.6),
        ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#1c2733")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE),
        ("LINEAFTER", (0, 0), (-2, -1), 0.4, RULE),
        ("BOX", (0, 0), (-1, -1), 0.5, RULE),
    ]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                  ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.6),
                  ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT])]
    t.setStyle(TableStyle(style))
    return [t, Spacer(1, 8)]


def code(text):
    return [Preformatted(text, S["code"]), Spacer(1, 8)]


# ---------------- header / footer ----------------
def _decorate(canvas, doc, first=False):
    canvas.saveState()
    w, h = LETTER
    # footer rule + text
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


def _first(canvas, doc):
    _decorate(canvas, doc, first=True)


def _later(canvas, doc):
    _decorate(canvas, doc, first=False)


# ---------------- content ----------------
SECTIONS = []   # (title, [flowables])


def sec(title, *blocks):
    flat = []
    for b in blocks:
        flat.extend(b if isinstance(b, list) else [b])
    SECTIONS.append((title, flat))


def h2(t):
    return Paragraph(t, S["h2"])


# 1
sec("ARCHITECTURE OVERVIEW",
    P("<b>ATLAS — Autonomous Tactical Learning Agentic System</b> — is an operating system for a "
      "Solutions Architect. It fuses two ideas. First, an <b>ontology-driven operating picture</b>: every "
      "entity the SA works with — customers, meetings, technologies, contacts, and deliverables — is a "
      "typed object linked into one navigable model, so the whole account history is a structured graph "
      "rather than scattered notes. Second, an <b>autonomous reasoning agent</b>: from a single command "
      "box it interprets intent, decomposes a goal into steps, dispatches parallel work, and synthesizes "
      "the result — acting on the SA's behalf rather than waiting for click-by-click instructions. The "
      "<b>Learning</b> dimension is cumulative: filed trip reports and artifacts continuously enrich each "
      "customer's profile, so the system gets sharper per account over time."),
    P("Its inference substrate is <b>Microsoft 365 Copilot driven through a real browser</b> "
      "(Selenium + persistent Edge/Chrome profiles) — with <b>no API keys, no tokens, and no admin "
      "scopes</b>. Whatever Copilot can see for the signed-in user, ATLAS can orchestrate. It is a "
      "desktop application (pywebview + WebView2) backed by a local HTTP server, a concurrent job "
      "engine, a skill registry, and a reasoning Brain."),
    P("ATLAS exists because the supported API path to grounded M365 Copilot requires admin consent and "
      "licensing that can take many months to obtain. Driving the licensed Copilot web app keeps all "
      "customer data inside the user's own Microsoft tenant boundary — no third-party LLM egress."),
    h2("What ATLAS Does"),
    bullets([
        "Reads the SA's calendar, meeting transcripts, emails, and files through Copilot <b>Work</b> mode",
        "Generates structured deliverables via <b>skills</b> — trip reports, battlecards, strategic "
        "briefings, account 360s, meeting prep, follow-ups, whitespace, topology, knowledge drops",
        "Runs a reasoning <b>Brain</b> over a free-text command box: classify intent, decompose multi-"
        "target goals, and fan out multi-agent <b>brainwaves</b>",
        "Builds and maintains an <b>Account Technology Profile</b> (ATP) per customer from filed trip reports",
        "Finds the right SHI engineer/vendor from a <b>People Resources</b> directory",
        "Runs scheduled instructions on a <b>Cron</b> daemon, in the user's timezone",
        "Logs <b>everything</b> as a searchable artifact, and every brain interaction as a reasoning receipt",
    ], numbered=True),
    h2("Request Lifecycle (Summary)"),
    table([["Layer", "Component", "Role"],
           ["1  UI", "atlas_web.py · index.html", "WebView2 single-page console; polls the API"],
           ["2  API", "atlas/web/{server,api}.py", "POST /api/<method> → Api.<method>; returns a job id"],
           ["3  Brain", "atlas/brain/router.py", "Classifies intent on Copilot Web vs. the manifest"],
           ["4  Jobs", "atlas/jobs/manager.py", "Worker-per-Chrome pool; runs the decision as jobs"],
           ["5  Engine", "atlas/engine/copilot.py", "Drives Copilot in the browser (Work/Web)"],
           ["6  Stores", "vault/ + atlas/store/*", "Customers, artifacts, ATP, settings, cron"]],
          [1.1, 2.0, 3.4]),
    h2("Key Design Decisions"),
    bullets([
        "<b>Browser-as-brain.</b> Copilot is the LLM; ATLAS runs threads of it in Work (tenant) or Web (public) mode.",
        "<b>Everything is an artifact.</b> Every deliverable and conversation is logged, readable in-app, searchable, and transferable.",
        "<b>Non-destructive.</b> Deletes are PIN-guarded soft-deletes to vault/recyclebin/; regeneration never clobbers hand-edits (pin-and-merge).",
        "<b>Concurrent &amp; resilient.</b> All real work runs as background jobs; jobs survive navigation and app restarts (vault/jobs.json).",
        "<b>Self-aware.</b> The Brain knows its own capabilities (the manifest) and rules, so it can say what it can do, can't do yet, or can't change.",
    ]))

# 2
sec("RUN MODEL & LAUNCH",
    P("ATLAS launches from <font face='Courier'>atlas.py</font> (or <font face='Courier'>atlas_web.py</font>). "
      "The launcher backfills trip-report artifacts, starts the API and the cron scheduler, then opens "
      "the WebView2 window that renders the single-page UI."),
    code("atlas.py  (launcher)\n"
         "  |- artifacts.backfill_trip_reports()   # every trip-report .md becomes an artifact\n"
         "  |- Api()                               # the facade the UI calls\n"
         "  |- ThreadingHTTPServer 127.0.0.1:<port>  (atlas/web/server.py)\n"
         "  |- scheduler.start_scheduler()         # Cron Jobs daemon\n"
         "  +- webview.create_window(...)          # WebView2 (Edge) renders index.html"),
    P("The UI is a <b>pull model</b>: the page polls <font face='Courier'>jobs()</font>, "
      "<font face='Courier'>days()</font>, and <font face='Courier'>artifacts()</font> roughly every "
      "1.5 seconds and re-renders. Long work never blocks the UI — it is a job on the engine pool."),
    h2("Prerequisites"),
    bullets([
        "Python 3.10+ with the project virtualenv (.venv) and requirements installed",
        "Microsoft Edge / Chrome with a signed-in M365 Copilot seed profile (cloned per pool slot)",
        "A licensed M365 Copilot account — no API keys, tokens, or admin scopes required",
    ]))

# 3
sec("THE HOME CONSOLE",
    P("The Home page is the command console — three columns under a <b>Working on</b> job bar (live "
      "spinner chips for active jobs, check/warn for finished)."),
    bullets([
        "<b>Left — Calendar.</b> Yesterday / Today / Tomorrow toggle. On boot, three gather_day jobs "
        "pull each day's meetings (cached to vault/daily/&lt;date&gt;/). A past meeting offers Create Trip Report.",
        "<b>Center — the command cluster</b> (scrollable). Five quick-nav buttons (Customer Vault · "
        "People Resources · Cron Jobs · Skills · Artifacts), the animated orb, the Brainwave History "
        "button, greeting + live date/time, the 3-row command box (the Brain), the <b>Continual "
        "Suggestions</b> panel, and — pinned at the bottom — Today's Scheduled Jobs (hidden when none).",
        "<b>Right — Recent Artifacts.</b> Newest-first deliverables (brainwaves excluded — they live in "
        "Brainwave History); 'open all' opens the Artifacts browser.",
    ]))

# 4
sec("SECTIONS & VIEWS",
    P("Top bar: Home · Settings · About. Customer Vault / People Resources / Cron Jobs / Skills / "
      "Artifacts are the five quick-nav buttons in the Home command cluster."),
    table([["Section", "What it does"],
           ["Home", "The console above."],
           ["Artifacts", "All deliverables/conversations (brainwaves excluded). Content search + 'Unfiled "
            "only' toggle; open & read, File to customer (file or transfer), Email (trip reports), PIN delete."],
           ["Customer Vault", "Searchable customer grid. A customer shows Trip Reports / ATP / Diagrams / "
            "Artifacts, an Overview + Key Contacts panel, a Generations picker, and Edit Technology "
            "Profile / Topology / Generate / Delete (PIN)."],
           ["Cron Jobs", "Schedule a free-text instruction + time + Daily/Weekly/Monthly; enable/disable/delete."],
           ["People Resources", "Browse/edit the SHI resource directory (PIN-gated); the find_resource skill."],
           ["Brainwave History", "Every brain-console interaction as a full reasoning receipt."],
           ["Settings", "Recipients, signature, auto-email, Timezone, System PIN, Brain Rules, Show Chrome windows."],
           ["Skills", "Grid of the 12 registered skills; run one directly with its input form."]],
          [1.4, 5.1]))

# 5
sec("THE BRAIN (ORCHESTRATION)",
    P("The command box is a <b>reasoning router</b>, not keyword matching. "
      "<font face='Courier'>command(text)</font> submits a <font face='Courier'>brain_route</font> job "
      "(Web mode); the Brain classifies intent against its capability manifest and acts."),
    code("command(text)\n"
         "  -> JobManager.submit('brain_route', {text}, mode='web')\n"
         "  -> _brain_route():\n"
         "       fast-path is_meta?                  -> answer from the manifest (no Copilot call)\n"
         "       fast-path meeting_trip_reports_day? -> trip_reports_day (regex, for cron reliability)\n"
         "       else router.classify(ask_web, text) -- Copilot WEB, grounded on the manifest\n"
         "            -> { action, skill, ctx, items[], collection, range, filter, explanation }\n"
         "       act on the decision  ->  log a Reasoning receipt to Brainwave History"),
    table([["Decision", "Behavior"],
           ["capabilities", "Answer 'what can you do / your skills' from the manifest."],
           ["run_skill", "Spawn the matched skill with extracted ctx (deliverable -> Artifacts)."],
           ["plan", "Decompose a multi-target goal into N parallel skill runs (Section 6)."],
           ["brainwave", "Spawn the multi-agent fan-out (Section 7)."],
           ["settings", "Return the exact pointer; ATLAS never changes its own settings."],
           ["cannot_do", "Explain why + recommend a skill to add (the 'planned' manifest entries seed this)."]],
          [1.3, 5.2]),
    P("<b>Grounding sources.</b> The capability manifest (atlas/brain/capabilities.py) auto-derives "
      "skills from the live registry; the Brain Rules (vault/brain/brain_rules.md) are a user-editable "
      "constitution injected into prompts (Rule #1: the customer's own saved data comes first)."))

# 6
sec("THE PLANNER & TIME REASONING",
    P("A skill acts on ONE target. When a request names <b>multiple</b> targets, the Brain returns "
      "<font face='Courier'>action=plan</font> and <font face='Courier'>_run_plan</font> fans out one "
      "skill job per target in parallel (pool runs 7 at a time, capped at 15/plan), each producing its "
      "own artifact, with one Plan receipt in Brainwave History."),
    bullets([
        "<b>items[]</b> — named targets (e.g. 'battlecards for AWC, ProPetro and Sendero' -> 3 jobs).",
        "<b>collection</b> — a set to resolve: yesterday_meetings / today_meetings / tomorrow_meetings / customers / date_range.",
    ]),
    h2("Time Reasoning & the Date-Range Coordinator"),
    P("The classifier is grounded with <b>today's absolute date</b>, so it resolves any time expression "
      "('May 21 to June 5', 'last two weeks') into absolute ISO dates and returns "
      "<font face='Courier'>collection=date_range</font> with a range and an optional "
      "<font face='Courier'>filter=external_customer</font>. The "
      "<font face='Courier'>skill_over_range</font> coordinator then:"),
    bullets([
        "splits the range into ~5-day <b>windows</b> (atlas/brain/timespan.py), each gathered in parallel "
        "on its own Chrome via gather_window (Copilot Work -> Graph calendar);",
        "de-dupes and drops obvious non-meetings (a conservative skip-list), then optionally runs a "
        "Copilot-Web pass to keep only external customer meetings;",
        "<b>reduces to the skill's granularity</b> — a meeting skill (trip_report) fans out per meeting; "
        "an account skill (strategic_briefing, battlecard) reduces to distinct customers and fans out per customer;",
        "fans out with a sliding-window dependency so only batch_concurrency (default 4) render at once "
        "— bounding RAM — capped at 40/job.",
    ], numbered=True),
    P("So 'trip reports for all my meetings May 21-June 5, external customers only' and 'strategic "
      "briefings for any external customer calls last week' both work — any skill over a span, at its "
      "natural granularity."))

# 7
sec("BRAINWAVES (MULTI-AGENT FAN-OUT)",
    P("For 'is &lt;product&gt; a good fit for &lt;customer&gt;?', the Brain creates a Brainwave History "
      "entry immediately (survives interruption), grounds on the customer's own saved data (Rule #1), "
      "then fans out <b>three parallel sub-agents</b> and synthesizes a grounded verdict."),
    table([["#", "Agent", "Mode", "Reads"],
           ["1", "Saved data", "Web", "the customer's actual trip-report content + ATP (chunk-fed)"],
           ["1", "Research", "Web", "public product research (architecture, competitors, pricing, fit)"],
           ["1", "Live check", "Work", "live M365 freshness / redundancy not in filed notes"],
           ["2", "Synthesis", "Web", "merges all three (wave.md) into a grounded verdict + trace"]],
          [0.3, 1.3, 0.7, 3.9]),
    P("Each sub-agent runs as its own job on a separate Chrome instance; their outputs merge into "
      "vault/brain/brainwaves/&lt;id&gt;/wave.md, and the synthesis runs on the facilitator thread. The "
      "history entry is then filled in with the verdict and an orchestration trace (which instance ran what)."))

# 8
sec("REASONING RECEIPTS",
    P("Every brain-console interaction logs a complete <b>Reasoning receipt</b> to Brainwave History so "
      "the caliber of each interaction can be judged. The receipt always carries the brain's logic; once "
      "any spawned work settles, a <font face='Courier'>finalize_receipt</font> job (gated on those jobs "
      "via after=, so it never blocks a pool worker) enriches it."),
    bullets([
        "<b>Brain logic</b> — the decision (action + skill/targets) and why; that classification ran on Copilot Web.",
        "<b>Agent trace</b> — a table: each agent/skill, Copilot Work/Web mode, the Chrome instance, and output size.",
        "<b>Rationale / logic of the answer</b> — for a single deliverable, a Copilot-Web pass explaining "
        "why this is the answer (e.g. why a chosen resource fits).",
        "<b>Technology used</b> — Copilot via the browser pool, and how many Chrome instances.",
    ]),
    P("Childless answers (capabilities / settings / cannot_do) finalize inline and read 'answered from "
      "the manifest — 0 Chrome instances,' which itself signals caliber."))

sec("CONTINUAL SUGGESTIONS",
    P("Because ATLAS stays open all day with idle agents and full calendar awareness, the Home screen "
      "shows a proactive <b>next-best-action</b> panel (<font face='Courier'>atlas/brain/suggest.py</font>), "
      "pinned above the scheduled-jobs strip. It only <b>suggests</b>; nothing runs until you tap a chip, "
      "which fires it as a normal, visible job. Two tiers:"),
    bullets([
        "<b>Tier 1 — instant (free, no Copilot).</b> Rule-based chips from local signals: the next "
        "meeting + its customer (meeting_prep, strategic_briefing), the focus customer, a recent "
        "trip-report customer (follow-up), and morning -> daily briefing. Computed fresh on every poll.",
        "<b>Tier 2 — strategic (Copilot-Web, throttled).</b> A <font face='Courier'>suggest</font> job "
        "reads the customer's saved data and returns up to 3 specific plays (LABEL :: COMMAND), cached to "
        "<font face='Courier'>vault/brain/suggestions.json</font>.",
    ]),
    h2("Refresh, Throttling & the Manual Button"),
    P("Tier 2 refreshes <b>event-driven</b> (a context key of focus-customer or next-meeting changes) "
      "plus a <b>frequency floor</b> (default 60 min), gated by work-hours and the AI toggle. "
      "<font face='Courier'>Api.suggestions()</font> serves Tier-1 fresh + Tier-2 cached (cached items "
      "show whenever recent, &lt;=6 h — context drift never hides them) and debounce-submits the job when "
      "due. <font face='Courier'>Api.request_suggestions()</font> backs the <b>Suggest now</b> button — "
      "forces a run immediately, bypassing the floor / work-hours / AI gate. Every run (manual or auto) "
      "leaves a 'Suggestions — …' record in Brainwave History and shows on the Working-on loader."),
    h2("Settings & Guardrails"),
    P("Five settings govern it: <font face='Courier'>continual_suggestions</font> (master), "
      "<font face='Courier'>suggestions_ai</font>, <font face='Courier'>suggestions_frequency_min</font> "
      "(30/60/120/240), <font face='Courier'>suggestions_focus_customer</font> (pin one customer, or "
      "auto = next meeting), <font face='Courier'>suggestions_workhours_only</font>. Guardrails: max 4 "
      "chips, dismissible, grounded in the real next-meeting/customer data, <b>suggest-not-act</b>, and "
      "throttled. Each tile shows a clear label, a faint command preview, and the full command on hover."))

# 9
sec("JOBS & CONCURRENCY",
    P("atlas/jobs/manager.py — the JobManager runs one <b>worker thread per Chrome slot</b> "
      "(POOL_SIZE = 7 -> up to 7 concurrent Copilot instances)."),
    bullets([
        "submit(kind, ctx, title, after=, icon=, mode=) -> a Job{kind, ctx, mode(work|web), status, after[], session_idx, log, result}.",
        "after= chains jobs; dependents release on any terminal state (_is_settled = done/error/interrupted), "
        "so a failed dependency never deadlocks its waiters — this makes the sliding-window throttle safe.",
        "Persisted to vault/jobs.json (survives restart; in-flight -> 'interrupted'). Idle Chrome auto-closes after 10s.",
    ]),
    h2("Job Kinds"),
    P("gather_day · the 12 skills · atp_generate · brain_route · brainwave · bw_research / bw_cust_saved / "
      "bw_cust_live · trip_reports_day · skill_over_range · gather_window · finalize_receipt · suggest "
      "(Continual Suggestions) · chat_continue. "
      "A plan decision fans out N ordinary skill jobs; skill_over_range does the same, throttled."))

# 10
sec("THE ENGINE (COPILOT-IN-A-BROWSER)",
    P("atlas/engine/{pool,copilot}.py. The EnginePool clones chrome_profile_0..6 from a signed-in seed; "
      "each is a Session with its own lock."),
    h2("Session Primitives"),
    table([["Primitive", "Purpose"],
           ["ask(prompt, mode)", "One question -> answer turn"],
           ["ask_chain(prompts)", "Several turns in ONE conversation; returns the last good answer"],
           ["ask_chain_all(prompts)", "Every turn's answer (chunked feeds)"],
           ["ask_at(url, prompt)", "Resume a saved conversation by its /chat/conversation/<id> URL"]],
          [1.9, 4.6]),
    h2("Completion, Guards & Long Context"),
    bullets([
        "<b>Work | Web</b> toggle per call (tenant grounding vs. public).",
        "<b>Completion</b> = the ATLAS-RESPONSE-COMPLETE marker, plus accept predicates (substantial &gt;400, "
        "brief &gt;80, feed_or_substantial) so Web answers finish even when the marker is dropped.",
        "<b>Echo guard</b> — _best_answer drops any block containing the sentinel hint, so an echoed pasted "
        "prompt is never captured as the answer.",
        "<b>Long context</b> is clipboard-pasted (&gt;2000 chars). After an answer, M365 rewrites the URL to "
        "/chat/conversation/<id>, captured for resume.",
        "<b>Hidden by default</b> — each Chrome launches off-screen and minimized so the pool never flashes "
        "windows; Settings -> 'Show the Copilot Chrome windows' surfaces them for debugging.",
    ]))

# 11
sec("SKILLS",
    P("Skills are self-registering units (atlas/skills/*.py) with typed inputs. The Brain routes to them, "
      "or run one directly from the Skills grid. Contract: Skill.run(ctx, ask, log) -> SkillResult."),
    table([["Skill", "Input(s)", "Produces"],
           ["trip_report", "meeting, date", "Structured trip report from a meeting transcript"],
           ["meeting_prep", "account, meeting", "Pre-meeting brief"],
           ["battlecard", "account", "Competitive battlecard"],
           ["strategic_briefing", "account", "Executive strategic briefing"],
           ["account_360", "account", "360-degree account overview"],
           ["follow_up", "account", "Follow-up plan / email"],
           ["whitespace", "account", "Whitespace / expansion opportunities"],
           ["environment_topology", "account", "Topology of the customer's environment"],
           ["find_resource", "need", "Best-fit SHI engineer/vendor from People Resources"],
           ["daily_briefing", "(none)", "Today's meetings with per-meeting prep"],
           ["knowledge_drop", "(none)", "Curated knowledge digest"],
           ["ask", "question", "General grounded Q&amp;A (a resumable chat)"]],
          [1.6, 1.6, 3.3]))

# 12
sec("PEOPLE RESOURCES",
    P("A CSV-backed directory of SHI engineers, vendors, assessments, and tool links. "
      "atlas/skills/peopleresources/resources.csv is the editable <b>source of truth</b> (migrated once "
      "from the original .xlsx). The store is atlas/store/people.py."),
    bullets([
        "<b>Browse / filter</b> — category chips + a live filter over name/specialty/region/practice/manager.",
        "<b>Edit (PIN-gated)</b> — add / edit / delete a resource; writes the CSV (the mirror).",
        "<b>Import</b> — drop a new CSV in import/, Import in-app; the prior CSV is archived to archive/ (never destroyed).",
        "<b>Brain skill</b> — find_resource answers 'a TOLA expert who can do PAM or EDR' via deterministic "
        "ranking; the Brain adds the rationale in the receipt.",
    ]))

# 13
sec("ATP SUBSYSTEM (ACCOUNT TECHNOLOGY PROFILE)",
    P("atlas/atp/* builds a per-customer technology profile from filed trip reports."),
    bullets([
        "<b>Generate</b> (extract.generate, Web): chunk all trip reports (~20K/turn, one conversation) -> "
        "technologies -> topology, a 3-paragraph overview, and key contacts; pin-and-merge keeps hand-edits; "
        "saved as a timestamped generation.",
        "<b>Relevancy</b> (recency.py): each tech shows 'appears in N trip reports' + 'last seen', computed from report dates.",
        "<b>Topology</b> (topology_html.py): glowing category columns, status-colored, click-for-specs.",
        "<b>Storage</b>: data_library.py, profile_store.py, generations.py (immutable snapshots).",
    ]))

# 14
sec("TRIP REPORTS & ARTIFACTS",
    P("Every deliverable and conversation is an <b>artifact</b> (vault/artifacts.json). Trip reports are "
      "first-class: backfilled from existing .md/.mht files at launch, content-searchable, readable in-app, "
      "transferable between customers, and emailable via Outlook."),
    bullets([
        "list_summaries (brainwaves excluded) · list_brainwaves · search · get · backfill_trip_reports · delete (soft, PIN) · uri_id_map",
        "File to customer files OR transfers an artifact between customers; brainwaves are multifaceted and not filed.",
    ]))

# 15
sec("CUSTOMER VAULT",
    P("Customers live under vault/customers/&lt;slug&gt;/ with trip_reports/, account_technology_profile/ "
      "(+ generations), network_diagrams/, artifacts/, and customer.json."),
    bullets([
        "Create / list / detail / assign_artifact (file or transfer) / delete_customer (PIN -> recyclebin).",
        "A customer page surfaces Overview + Key Contacts, the ATP editor, Topology, Generate, and Generations picker.",
    ]))

# 16
sec("CRON SCHEDULER",
    P("atlas/jobs/scheduler.py is a daemon (started at launch) that ticks ~every 30s, computes 'now' in "
      "the Settings timezone, and fires any due cron by submitting a brain_route job with the instruction "
      "— exactly as if typed. So a cron gets the full Brain: planning, date ranges, brainwaves."),
    bullets([
        "Due = now >= today@HH:MM, the day matches Daily/Weekly/Monthly, and last_fired != today.",
        "vault/cron.json is the source of truth. Example: '5pm — create trip reports for all of today's external meetings.'",
    ]))

# 17
sec("STORES & DATA LAYOUT",
    code("vault/\n"
         "  customers/<slug>/\n"
         "    trip_reports/*.md                       # each is an artifact\n"
         "    account_technology_profile/  (+ generations/<ts>/)\n"
         "    network_diagrams/  artifacts/  customer.json\n"
         "  artifacts.json        # deliverables + conversations + brainwaves\n"
         "  jobs.json             # job history (status bar)\n"
         "  settings.json         # recipients, signature, tz, system_pin, show_chrome_windows,\n"
         "                        #   gather_window_size, batch_concurrency\n"
         "  cron.json             # scheduled instructions\n"
         "  brain/ brain_rules.md · brainwaves/<id>/wave.md\n"
         "  recyclebin/           # soft-deleted customers + artifacts (never auto-purged)\n"
         "  daily/<date>/briefing.json   exports/   inbox/"),
    h2("Concurrency-Safe Writes"),
    P("The pool runs many worker threads that write vault/artifacts.json at once, so the store does an "
      "<b>atomic write</b> (temp file -> os.replace) under a <b>module lock</b> around every "
      "load->mutate->save. <font face='Courier'>_load</font> is <b>self-healing</b>: on a corrupt file it "
      "backs up to artifacts.json.corrupt-&lt;UTC&gt;, salvages every intact record (brace-match + de-dupe "
      "by id), rewrites a clean file, and never silently returns an empty list for populated-but-broken data."))

# 18
sec("SETTINGS",
    table([["Setting", "Purpose"],
           ["trip_report_recipients", "Comma/semicolon emails the Email button pre-fills"],
           ["email_signature", "Appended under the report body in the draft"],
           ["auto_email_trip_reports", "Auto-open an Outlook draft when a trip report finishes"],
           ["timezone", "IANA timezone the Cron scheduler fires in"],
           ["system_pin", "6-digit PIN required for any delete (blank disables deletion)"],
           ["show_chrome_windows", "Debug: launch the pool's Chrome on-screen (default off = hidden)"],
           ["gather_window_size", "Days per parallel meeting-gather window (default 5)"],
           ["batch_concurrency", "Max deliverables rendering at once in a fan-out (default 4)"],
           ["continual_suggestions", "Master on/off for the Continual Suggestions panel"],
           ["suggestions_ai", "Tier-2 strategic (Copilot) suggestions on/off"],
           ["suggestions_frequency_min", "Min minutes between Tier-2 refreshes (30/60/120/240)"],
           ["suggestions_focus_customer", "Pin advice to one customer; blank = auto (next meeting)"],
           ["suggestions_workhours_only", "Only generate Tier-2 ~7am-7pm"],
           ["Brain Rules", "Editable constitution injected into the Brain's prompts"]],
          [2.1, 4.4]),
    P("ATLAS never changes its own settings — the Brain points the user to the Settings page instead."))

# 19
sec("CAPABILITY MANIFEST & BRAIN RULES",
    P("The Brain introspects two sources. The <b>capability manifest</b> (atlas/brain/capabilities.py) "
      "auto-derives skill entries from the live registry plus engine/vault/ATP/settings-pointer/planned "
      "entries, so it never drifts. <font face='Courier'>human_summary()</font> answers 'what can you do'; "
      "<font face='Courier'>describe()</font> renders the planner-prompt block."),
    P("The <b>Brain Rules</b> (vault/brain/brain_rules.md) are a user-editable constitution read on every "
      "brainwave and injected into the saved-analysis, freshness, and synthesis prompts. Rule #1: the "
      "customer's organized artifacts are the #1 source. Edited in Settings -> Brain Rules."))

# 20
sec("SECURITY & DATA BOUNDARY",
    bullets([
        "<b>No API keys, tokens, or admin scopes.</b> Inference rides the user's licensed Copilot web session.",
        "<b>Data stays in tenant.</b> Customer data does not egress to a third-party LLM API — a key advantage of the browser approach.",
        "<b>Destructive actions guarded.</b> Deletes require a 6-digit System PIN and are soft-deletes to recyclebin/ — never hard deletes.",
        "<b>Secrets.</b> Any credential (e.g. an Entra app secret, if APIs are later enabled) lives only in .env — never in code or the vault.",
        "<b>Sign-in recovery.</b> If a Chrome profile is logged out, the engine surfaces that window on-screen and prompts the user to sign in, then resumes.",
    ]))

# 21
sec("FILE MAP",
    code("hackathonsandbox/\n"
         "  atlas.py / atlas_web.py            launchers\n"
         "  config.py                          POOL_SIZE, vault dirs, RECYCLEBIN_DIR, CRON_PATH, PEOPLE_*\n"
         "  atlas/\n"
         "    web/ server.py · api.py (~40 methods) · index.html\n"
         "    brain/ capabilities.py · router.py · brainwave.py · rules.py · timespan.py · suggest.py\n"
         "    jobs/ manager.py · scheduler.py\n"
         "    engine/ pool.py · copilot.py\n"
         "    skills/ base.py + 12 skills · peopleresources/ (find_resource + resources.csv)\n"
         "    store/ vault · customers · artifacts · settings · cron · people\n"
         "    atp/ extract · generations · recency · topology_html · data_library · profile_store\n"
         "  vault/                              all runtime data (see Section 17)\n"
         "  ATLAS_ARCHITECTURE.md / .drawio     master architecture reference + one-page diagram\n"
         "  SHI_ATLAS_Engineering_Documentation.pdf   (this document)"))

# 22
sec("CONFIGURATION REFERENCE",
    h2("config.py"),
    code("POOL_SIZE        = 7        # concurrent Chrome instances (env ATLAS_POOL_SIZE)\n"
         "VAULT_DIR        = .../vault\n"
         "CUSTOMERS_DIR    = VAULT_DIR / 'customers'\n"
         "RECYCLEBIN_DIR   = VAULT_DIR / 'recyclebin'\n"
         "CRON_PATH        = VAULT_DIR / 'cron.json'\n"
         "PEOPLE_CSV       = atlas/skills/peopleresources/resources.csv   # source of truth"),
    h2("Engine / Accept Predicates"),
    bullets([
        "ATLAS-RESPONSE-COMPLETE marker + accept: substantial (>400 chars), brief (>80), feed_or_substantial.",
        "Long prompts (>2000 chars) are clipboard-pasted; conversation URL captured for resume.",
    ]),
    h2("Brain / Fan-out Knobs"),
    bullets([
        "gather_window_size (5) — days per parallel gather window.",
        "batch_concurrency (4) — max deliverables rendering at once (sliding-window after[]).",
        "plan cap 15 targets; date-range fan-out cap 40; span cap ~60 days.",
    ]))

# 23
sec("TROUBLESHOOTING",
    table([["Symptom", "Cause & Fix"],
           ["Brainwave History empty", "vault/artifacts.json was corrupted; the self-healing loader backs "
            "it up (corrupt-<UTC>) and salvages on next load. Relaunch ATLAS."],
           ["A Copilot window opens and waits", "The M365 session is signed out. Sign in to the surfaced "
            "Chrome window; the job resumes."],
           ["'No today meetings to report on'", "Use an explicit date or range ('May 21 to June 5'); the "
            "Brain resolves spans and gathers in parallel."],
           ["Chrome windows flash on screen", "Settings -> turn OFF 'Show the Copilot Chrome windows' "
            "(default hidden/minimized)."],
           ["A skill ran instead of a rationale", "Receipts now always include the rationale + agent trace; "
            "open the entry in Brainwave History."],
           ["Reports dated wrong", "Trip reports are stamped with the meeting's own date, not today's."]],
          [2.0, 4.5]))


# ---------------- build ----------------
def build():
    doc = BaseDocTemplate(OUT, pagesize=LETTER,
                          leftMargin=0.8 * inch, rightMargin=0.8 * inch,
                          topMargin=0.85 * inch, bottomMargin=0.8 * inch,
                          title="A.T.L.A.S. — Engineering Documentation", author="Manuel Zelaya")
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="main")
    doc.addPageTemplates([
        PageTemplate(id="first", frames=[frame], onPage=_first),
        PageTemplate(id="later", frames=[frame], onPage=_later),
    ])

    story = []
    # ----- title page -----
    story += [Spacer(1, 1.7 * inch),
              Paragraph("A.T.L.A.S.", S["title"]),
              Paragraph("Autonomous Tactical Learning Agentic System", S["subtitle"]),
              Spacer(1, 8),
              Paragraph("Engineering Documentation", S["tpb"]),
              Spacer(1, 6),
              Paragraph("An ontology-driven, autonomously-reasoning operating system for a Solutions Architect", S["tag"]),
              Paragraph("Microsoft 365 Copilot-in-a-browser  |  Reasoning Brain  |  7 concurrent agents  |  No API keys", S["tag"]),
              Spacer(1, 1.4 * inch),
              Paragraph("Manuel Zelaya", S["tpb"]),
              Paragraph("Solutions Architect", S["tp"]),
              Spacer(1, 6),
              Paragraph("Version 1.0  |  June 2026", S["tp"]),
              Paragraph("SHI International Corp.  |  Solutions Engineering", S["tp"]),
              Spacer(1, 24),
              Paragraph("CONFIDENTIAL", S["tpb"]),
              NextPageTemplate("later"), PageBreak()]

    # ----- TOC -----
    def _toc_label(t):
        lbl = t.title()
        for a, b in (("Atp", "ATP"), ("Copilot-In-A-Browser", "Copilot-in-a-Browser"),
                     ("Ucc", "UCC"), ("Iot", "IoT"), (" & ", " &amp; ")):
            lbl = lbl.replace(a, b)
        return lbl

    story.append(Paragraph("TABLE OF CONTENTS", S["h1"]))
    for i, (t, _) in enumerate(SECTIONS, 1):
        story.append(Paragraph(f"{i}&nbsp;&nbsp;&nbsp;{_toc_label(t)}", S["toc"]))
    story.append(PageBreak())

    # ----- sections -----
    for i, (t, blocks) in enumerate(SECTIONS, 1):
        story.append(Paragraph(f"{i}.&nbsp;&nbsp;{t}", S["h1"]))
        story += blocks
        story.append(Spacer(1, 4))

    doc.build(story)
    print("wrote", OUT)


if __name__ == "__main__":
    build()
