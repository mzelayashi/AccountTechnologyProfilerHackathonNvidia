"""Generate ATP_Engineering_Document.pdf — the deep technical engineering reference for ATP
(Account Technology Profiler), the local-NVIDIA-Nemotron agentic SA operating system.

Title page + running header/footer, numbered TOC, UPPERCASE section headers, tables, lists, code
blocks, file map. Run:  .venv/bin/python build_atp_engineering_doc.py
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

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ATP_Engineering_Document.pdf")
NAVY = colors.HexColor("#13243a")
ACCENT = colors.HexColor("#1f6f8b")
TEAL = colors.HexColor("#2aa0a4")
GREY = colors.HexColor("#6e7681")
LIGHT = colors.HexColor("#eef3f8")
RULE = colors.HexColor("#c7d3e0")
HEADER_TXT = "ATP   |   Engineering Document"
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
sec("ARCHITECTURE OVERVIEW",
    P("<b>ATP — Account Technology Profiler</b> — is an autonomous, agentic operating system for a "
      "Solutions Architect. From a single command box it interprets intent, decomposes goals, dispatches "
      "parallel work, reasons over a per-customer technology profile, and synthesizes cited deliverables. "
      "Its defining property is that it runs on a <b>self-hosted NVIDIA model</b>: "
      "<font face='Courier'>nvidia/Llama-3_3-Nemotron-Super-49B-v1_5</font> served by <b>vLLM</b> across "
      "<b>two H100 NVL GPUs</b> at tensor-parallel = 2 — with <b>no API keys, no cloud LLM, and no "
      "customer-data egress</b>."),
    P("ATP descends from ATLAS, whose inference substrate was Microsoft 365 Copilot driven through a "
      "browser (Selenium + a pool of Chrome agents). ATP replaces that substrate wholesale with local "
      "Nemotron inference. The Copilot/Chrome engine is hard-disabled "
      "(<font face='Courier'>ATLAS_COPILOT_DISABLED=1</font>); the browser pool, M365 calendar ingestion, "
      "and Selenium agents are retired. The application shell, the concurrent job engine, the vault, the "
      "skill registry, and the agentic patterns were preserved and re-grounded on Nemotron."),
    h2("Request Lifecycle"),
    table([["Layer", "Component", "Role"],
           ["1  UI", "atlas/web/index.html · run_atlas_linux.py", "Local single-page console (Chrome app-mode); pull model"],
           ["2  API", "atlas/web/{server,api}.py", "POST /api/<method> → Api.<method>; returns a job id / JSON"],
           ["3  Guardrails", "atlas/brain/guardrails.py", "Optional input rail on command() (off by default)"],
           ["4  Brain", "atlas/brain/nemotron_brain.py", "Nemotron classify → run_skill / navigate / rag / research / brainwave"],
           ["5  Jobs", "atlas/jobs/manager.py", "Worker pool; runs the decision as cancellable jobs"],
           ["6  Engine", "atlas/engine/nemotron.py · websearch.py", "Local Nemotron client + live web research"],
           ["7  Stores", "vault/ + atlas/store/* + atlas/atp/*", "Customers, artifacts, ATP, settings, recyclebin"]],
          [1.0, 2.6, 2.9]),
    h2("Key Design Decisions"),
    bullets([
        "<b>Sovereign local inference.</b> Nemotron-49B runs on the user's own 2× H100s via vLLM; the same OpenAI-compatible client is NIM-ready (one env var to repoint).",
        "<b>Everything is an artifact.</b> Every deliverable and brain interaction is logged, in-app readable, searchable, and (where applicable) transferable to a customer.",
        "<b>Non-destructive.</b> Deletes are PIN-guarded soft-deletes to vault/recyclebin/; ATP regeneration never clobbers hand-edits (pin-and-merge).",
        "<b>Concurrent &amp; cancellable.</b> All real work is a background job; jobs survive navigation/restarts; the ✕ recursively cancels a job tree and aborts in-flight generation.",
        "<b>Self-aware &amp; auditable.</b> Every command yields a reasoning receipt in Brainwave History (decision, engine-aware agent trace, rationale, self-check).",
    ]))

# 2
sec("RUN MODEL & LAUNCH",
    P("ATP launches from <font face='Courier'>run_atlas_linux.py</font> with "
      "<font face='Courier'>ATLAS_COPILOT_DISABLED=1</font>. It backfills trip-report artifacts, starts "
      "the API server, and blocks (the UI is opened separately as a Chrome app-mode window, e.g. via the "
      "ATP desktop shortcut). The cron scheduler and calendar auto-refresh are intentionally NOT started "
      "(they drove M365/Chrome)."),
    code("run_atlas_linux.py\n"
         "  ATLAS_COPILOT_DISABLED=1            # hard backstop: no browser may launch\n"
         "  artifacts.backfill_trip_reports()  # every trip-report .md → artifact\n"
         "  Api()                              # the facade the UI calls\n"
         "  ThreadingHTTPServer 127.0.0.1:8080 (atlas/web/server.py)\n"
         "  threading.Event().wait()           # server runs in a daemon thread"),
    P("The UI is a <b>pull model</b>: the page polls jobs/artifacts (~1.5 s, no-store) and re-renders. "
      "Long work is always a background job — it never blocks the UI."),
    h2("vLLM serving (the model)"),
    P("vLLM is managed out-of-process by <font face='Courier'>~/vllm_service_manager.sh</font> in a tmux "
      "session named <font face='Courier'>ai</font>. Launch flags:"),
    code("VLLM_USE_FLASHINFER_SAMPLER=0 python -m vllm.entrypoints.openai.api_server \\\n"
         "  --model nvidia/Llama-3_3-Nemotron-Super-49B-v1_5 --trust-remote-code \\\n"
         "  --host 0.0.0.0 --port 8000 \\\n"
         "  --served-model-name Llama-3_3-Nemotron-Super-49B-v1_5 \\\n"
         "  --tensor-parallel-size 2 --gpu-memory-utilization 0.85 \\\n"
         "  --max-model-len 8192 --enforce-eager"),
    bullets([
        "<b>TP=2</b> shards the 49B weights across both H100 NVL cards (~82 GB resident per card).",
        "<b>8192 context.</b> The 32K FlashInfer path needs a CUDA toolkit (nvcc) not installed here; VLLM_USE_FLASHINFER_SAMPLER=0 uses the native sampler at 8K.",
        "Manager menu: status · start · graceful stop · restart · quick-recover · GPU topology · attach · tail logs.",
    ]))

# 3
sec("THE NEMOTRON ENGINE",
    P("<font face='Courier'>atlas/engine/nemotron.py</font> is the single inference client. It is "
      "ENV-driven so the same code targets local vLLM or an NVIDIA NIM:"),
    code("LLM_BASE_URL  http://localhost:8000/v1     # or a NIM endpoint\n"
         "LLM_MODEL     Llama-3_3-Nemotron-Super-49B-v1_5\n"
         "LLM_API_KEY   dummy                         # vLLM ignores it; SDK requires a value\n\n"
         "complete(prompt, *, system='detailed thinking off', temperature=0.6, top_p=0.95,\n"
         "         max_tokens=None, retries=2, on_log=None, should_cancel=None) -> str"),
    h2("Nemotron quirks handled"),
    bullets([
        "<b>&lt;think&gt; block.</b> The model always emits &lt;think&gt;…&lt;/think&gt; reasoning; strip_think() removes it before returning.",
        "<b>Sampling.</b> Greedy (temp 0) loops; NVIDIA's recommended temp 0.6 / top_p 0.95 is the default.",
        "<b>Token budgeting.</b> The live max_model_len is read from /v1/models; when max_tokens is None it is budgeted as window − est(prompt)×1.5 − margin (capped) so prompt + reasoning + answer fit 8K.",
    ]),
    h2("Streaming cancellation (free the GPU)"),
    P("When <font face='Courier'>should_cancel</font> is supplied, the request is streamed and the flag "
      "is polled between chunks; on cancel the stream is closed (vLLM stops generating) and a "
      "<font face='Courier'>Cancelled</font> exception is raised. This is the local-model analog of "
      "closing a browser tab — the worker unwinds and the GPU is freed immediately."),
    h2("Context-overflow self-correction"),
    P("If vLLM rejects a request for exceeding 8192 tokens, the 400 error reports the real prompt size "
      "(‘N in the messages’). complete() parses N and retries with max_tokens shrunk to fit — so a "
      "mis-estimated prompt self-corrects instead of failing."))

# 4
sec("THE BRAIN — INTENT ROUTING",
    P("<font face='Courier'>atlas/brain/nemotron_brain.py</font> + "
      "<font face='Courier'>JobManager._brain_route_nemotron</font> route a free-text command through one "
      "Nemotron classification call into five actions."),
    table([["Action", "Trigger (example)", "Behavior"],
           ["run_skill", "“strategic briefing for Acme”", "Dispatch the skill job for the resolved customer"],
           ["navigate", "“create a network diagram for Acme”", "Tell the user to open Skills → the interactive tool"],
           ["rag", "“which customers use Palo Alto?”", "Cited retrieval over the Customer Vault (§6)"],
           ["research", "“research the latest Palo Alto firewalls”", "Live web-research agent (§7)"],
           ["brainwave", "“is Verkada a good fit for Acme?”", "Multi-agent fan-out + self-check (§8)"]],
          [1.1, 2.5, 2.9]),
    h2("Skill grounding without per-skill rewrites"),
    P("The Copilot-era data skills (strategic_briefing, account_360, battlecard, whitespace, follow_up, "
      "environment_topology) call an <font face='Courier'>ask()</font> that assumed M365 grounding. On "
      "Nemotron the job runner rebuilds that closure as "
      "<font face='Courier'>ask = lambda p: nemotron.complete(saved_context(customer) + p)</font> — the "
      "customer's saved ATP profile + recent trip reports (hard-capped to fit 8K) are prefixed onto the "
      "skill's own prompt. The skills produce real grounded JSON/markdown/diagrams with <b>zero per-skill "
      "code changes</b>."),
    h2("Reasoning receipts (engine-aware)"),
    P("Every interaction writes a Brainwave-History receipt: the decision line (“decided "
      "<b>run_skill</b> → strategic_briefing”), grounding (“routed on <b>local Nemotron</b>”), an "
      "agent trace table whose Engine column reads <font face='Courier'>Nemotron-49B (vLLM·2×H100)</font>, "
      "and a model-generated rationale (the ‘why’). The receipt machinery is engine-aware — no "
      "Copilot/Chrome/Selenium wording in the local build — and a finalize_receipt job enriches it after "
      "the spawned work settles."))

# 5
sec("VAULT RAG — RETRIEVAL OVER CUSTOMERS",
    P("<font face='Courier'>nemotron_brain.rag_answer()</font> answers questions across one, several, or "
      "<b>all</b> customers."),
    bullets([
        "<b>Scope + terms.</b> A quick Nemotron parse decides scope (named vs all) and the search terms, with a deterministic fallback; names resolve to vault slugs via resolve_customer.",
        "<b>Deterministic retrieval (cheap, scales to ~84 customers).</b> Per customer it scans data_library.json (vendor/product/category/notes), trip_reports/*.md (line snippets), overview.json, vision/network *.xlsx cell text, and the customer's artifacts — collecting bounded {customer, source, detail} hits.",
        "<b>Cited synthesis.</b> Nemotron writes a markdown answer that cites where each fact was found, treating the ‘## &lt;Customer&gt;’ header as authoritative (so leftover names inside content don't misattribute), and says plainly when nothing matched.",
    ]),
    P("The customer scan loop and synthesis honor should_cancel, so a long ‘all customers’ query stops "
      "promptly when the job is cancelled."))

# 6
sec("LIVE WEB RESEARCH",
    P("<font face='Courier'>atlas/engine/websearch.py</font> (httpx + lxml; no API key) is the only "
      "outbound path. <font face='Courier'>search()</font> queries DuckDuckGo (lite, then html), unwraps "
      "redirect links, and drops results whose host matches a Guardrails-blocked domain. "
      "<font face='Courier'>fetch()</font> extracts readable page text. "
      "<font face='Courier'>research_brief()</font> returns a compact numbered SOURCES block (top results "
      "+ the first few fetched pages). If egress fails, it returns empty and the agent falls back to model "
      "knowledge with a logged note."))

# 7
sec("THE BRAINWAVE — MULTI-AGENT FAN-OUT",
    P("For “is &lt;product&gt; a good fit for &lt;customer&gt;?”, "
      "<font face='Courier'>JobManager._brainwave_nemotron</font> orchestrates a parallel agent graph:"),
    bullets([
        "<b>Fan out two agents in parallel</b> (each a real job on its own worker → genuine concurrent inference batched on the H100s): 🔎 bw_research (live web research → Nemotron brief) ∥ 🗂 bw_cust_saved (Nemotron over the customer's saved data).",
        "<b>Merge</b> both into an ephemeral wave.md.",
        "<b>🧬 synthesis agent</b> — a grounded verdict (Verdict / Where it fits / Risks &amp; objections / Recommended next step), citing the customer's real stack.",
        "<b>🔎 self-check agent</b> — a separate Nemotron pass fact-checks the verdict against the evidence, flagging unsupported claims with a confidence rating (‘the brain checks its own work’).",
        "<b>Audit receipt</b> — a brainwave artifact records the parallel-agent trace, the verdict, and the self-check in Brainwave History.",
    ]),
    P("Cancelling the brainwave recursively cancels its sub-agents, skips synthesis/self-check, and marks "
      "the in-progress artifact ‘⏹ cancelled’. The M365 live-tenant freshness agent from the Copilot "
      "era is dropped (no tenant)."))

# 8
sec("THE JOB ENGINE",
    P("<font face='Courier'>atlas/jobs/manager.py</font> runs a Job queue on a worker pool "
      "(POOL_SIZE = 4). Each request is a Job mirrored to vault/jobs.json (survives restarts)."),
    h2("Recursive, abortable cancellation"),
    P("submit(kind, ctx, …, parent=) links sub-jobs into a tree. cancel(jid) walks the job + all "
      "descendants and, for each, sets the per-job cancel flag (polled by the streaming nemotron.complete "
      "to abort mid-generation and free the GPU). A cancelled brainwave stops its research/customer "
      "sub-agents, skips downstream work, and cleans its artifact."),
    h2("Job kinds"),
    code("brain_route        the Brain (route + dispatch)\n"
         "brainwave          multi-agent fan-out facilitator\n"
         "bw_research        🔎 web research sub-agent\n"
         "bw_cust_saved      🗂 customer-infrastructure sub-agent\n"
         "web_research       standalone research action (§6)\n"
         "docx_network       Word .docx → Nemotron → network intake → map\n"
         "vision_generate    text → combined current/future vision .drawio\n"
         "atp_generate       map-reduce ATP profile build\n"
         "<skill kinds>      strategic_briefing, battlecard, … (grounded)\n"
         "finalize_receipt   enriches a brainwave receipt after children settle"))

# 9
sec("SKILLS REGISTRY & SEDRAW",
    P("Skills are <font face='Courier'>Skill.run(ctx, ask, log) → SkillResult</font>. For the demo the "
      "Skills page shows only the interactive SEdraw tools; the rest remain registered and Brain-runnable "
      "(a single _HIDDEN_SKILLS filter in api.skills() — nothing is deleted)."),
    h2("SEdraw — Network Diagrams"),
    bullets([
        "Excel intake (network_input/*.xlsx; sites → categories with Qty×Model + connections) → NetworkTopologyGenerator → multi-site .drawio + a self-contained diagrams.net viewer.",
        "Full in-GUI editor; ＋ Create New blank template; per-file 🗑 PIN soft-delete.",
        "<b>📄 Convert from DOCX.</b> docx_to_network.py extracts a Word intake (python-docx: paragraphs + tables), Nemotron maps it onto the 23 valid network categories (best-effort, omits what doesn't fit), writes the intake .xlsx, and generates the map — a cancellable docx_network job. The .xlsx is editable + regenerable.",
    ]),
    h2("SEdraw — Vision Boards (Vision Studio)"),
    bullets([
        "Two free-text boxes (current / future state) → Nemotron (vision_ai.py) → one combined diagram (current top, future bottom) → VisionBoardGenerator .drawio + viewer.",
        "Runs as a background vision_generate job (tasks bar + artifact); history loads older sessions; full editor; backend .xlsx hidden, named customer+date; per-session 🗑 soft-delete.",
    ]))

# 10
sec("ATP SUBSYSTEM",
    P("<font face='Courier'>atlas/atp/*.py</font> builds and maintains the per-customer technology "
      "profile from filed trip reports."),
    bullets([
        "<b>extract.generate_local(ask, customer, log)</b> — map-reduce: chunk the trip-report text to fit 8K, run TECH / OVERVIEW / CONTACTS prompts per chunk concurrently (thread pool), then reduce (merge technologies, clean+merge contacts, synthesize overview). No browser.",
        "<b>generations.py</b> — each ‘✨ Generate’ is an immutable timestamped snapshot under account_technology_profile/generations/&lt;id&gt;/; the live flat files are the editable working copy; pin-and-merge means hand-edits survive regeneration. Per-snapshot 🗑 delete (live ‘Current’ protected).",
        "<b>data_library / profile_store / recency / topology_html</b> — structured tech inventory (vendor, product, category, deployment status, mention_count, last_seen), overview + contacts stores, recency scoring, rendered topology.",
    ]))

# 11
sec("CUSTOMER VAULT & SOFT-DELETE",
    code("vault/customers/<slug>/\n"
         "  trip_reports/                 filed .md trip reports\n"
         "  account_technology_profile/   data_library.json · overview.json · contacts.json\n"
         "    generations/<id>/           immutable snapshots\n"
         "  network_input/  network_output/   SEdraw network .xlsx / .drawio\n"
         "  vision_input/   vision_output/    SEdraw vision .xlsx / .drawio\n"
         "  artifacts/                    filed deliverables"),
    P("Customer display names in the demo vault are anonymized (folder/display only). All deletes — a "
      "customer, an artifact, a vision board, a network diagram, or a topology generation — are "
      "<b>PIN-guarded soft-deletes</b> that move the file(s) to <font face='Courier'>vault/recyclebin/</font> "
      "(they vanish from the UI but are never erased). The 6-digit System PIN (Settings) is required; if "
      "unset, deletion is blocked. One shared frontend pinDeleteModal + matching PIN-checked endpoints "
      "(delete_customer/artifact/generation, sedraw_vision_delete, sedraw_network_delete)."))

# 12
sec("NEMO GUARDRAILS",
    P("A NeMo Guardrails input self-check rail on the command box, running on the local Nemotron. "
      "<b>OFF by default, fail-open</b> (any error → allow), with a native fallback."),
    h2("Three-tier evaluation"),
    bullets([
        "<b>1. Deterministic denylist</b> — blocked words (instant, no model call).",
        "<b>2. NeMo Guardrails LLMRails</b> — the real ‘self_check_input’ rail on local Nemotron (OpenAI provider → LLM_BASE_URL).",
        "<b>3. Native fallback</b> — a tiny Nemotron yes/no classifier if the package can't load.",
    ]),
    h2("Levers (settings.json) & wiring"),
    bullets([
        "master on/off · keep on-topic · block unsafe · block prompt-injection · strictness (lenient/balanced/strict) · blocked words · blocked research domains.",
        "Changing levers regenerates guardrails_config/prompts.yml and rebuilds the cached rail.",
        "Api.command() calls check_input first; a block returns a refusal (no job) and records to a shared cross-process log vault/guardrails_blocks.json.",
        "guardrails_config/: config.yml (rails + model), prompts.yml (self_check_input), rails.co (refusal message). Input self-check only — no Colang dialog flows / embedding models (light, fully offline).",
    ]),
    h2("Standalone Control Panel"),
    P("<font face='Courier'>guardrails_panel.py</font> is a separate stdlib web app on :8090 (own process, "
      "own Desktop shortcut) that reads/writes the same guardrails_* settings — so it governs the live "
      "rail — but cannot crash ATP. It exposes the levers, a live Test box (ALLOW/REFUSE + reason + which "
      "engine ran), and a Recent-blocks log that reads the shared file and auto-refreshes every 4 s."))

# 13
sec("OPERATIONS & SCRIPTS",
    table([["Script", "Purpose"],
           ["demo_health.sh", "Pre-demo board: 2×H100, weights resident (TP=2), vLLM health, live generation (latency/tok-s), ATP app — each green. --recover / --restart / --manage delegate to the vLLM manager."],
           ["guardrails.sh on|off|status", "Terminal toggle for the command-box rail (next command; no restart)."],
           ["guardrails_panel.sh", "Launch the Guardrails Control Panel (:8090)."],
           ["launch_guardrails_panel.sh", "Desktop-shortcut launcher (starts panel if down + opens app window)."],
           ["run_atlas_linux.py", "Launch the ATP app server (Copilot/Chrome disabled)."],
           ["~/vllm_service_manager.sh", "vLLM lifecycle in tmux 'ai': status/start/stop/restart/recover/topology/attach/logs."]],
          [2.4, 5.0]))

# 14
sec("SECURITY & DATA BOUNDARY",
    bullets([
        "<b>Sovereign, local inference.</b> The model runs on the user's own 2×H100s. No API keys, no cloud LLM, no customer-data egress.",
        "<b>One opt-in network path.</b> The web-research agent makes outbound DuckDuckGo/page requests — only the query leaves the box, only when the user runs research/brainwave; domains can be denylisted.",
        "<b>PIN-guarded, non-destructive.</b> All deletes are soft-deletes to recyclebin/, gated by the System PIN.",
        "<b>Guardrails.</b> The command box can be governed (topical/safety/injection + denylists) with a full audit log.",
        "<b>NIM-ready.</b> Repointing to an NVIDIA NIM (local or hosted) is a single env var (LLM_BASE_URL).",
    ]))

# 15
sec("FILE MAP",
    code("~/ATLAS/\n"
         "  run_atlas_linux.py · config.py\n"
         "  atlas/\n"
         "    web/   server.py · api.py · index.html\n"
         "    brain/ nemotron_brain.py · guardrails.py · guardrails_config/ ·\n"
         "           brainwave.py · capabilities.py · rules.py · router.py (legacy)\n"
         "    engine/ nemotron.py · websearch.py · pool.py · copilot.py (disabled)\n"
         "    jobs/  manager.py · scheduler.py\n"
         "    skills/ base.py + skills · peopleresources/\n"
         "    sedraw/ network_*.py · drawio_generator.py · vision_ai.py · docx_to_network.py · service.py\n"
         "    atp/   extract · generations · recency · topology_html · data_library · profile_store\n"
         "    store/ vault · customers · artifacts · settings · cron · people\n"
         "  guardrails_panel.py · demo_health.sh · guardrails.sh · guardrails_panel.sh\n"
         "  ATP_ARCHITECTURE.md/.drawio · GUARDRAILS_ARCHITECTURE.drawio · NEMOTRON_ARCHITECTURE.md\n"
         "  ATP_Engineering_Document.pdf · ATP_User_Guide.pdf\n"
         "  vault/  (runtime data + recyclebin/ + guardrails_blocks.json + jobs.json)\n"
         "~/vllm_service_manager.sh"))

# 16
sec("CONFIGURATION REFERENCE",
    table([["Key / env", "Default", "Purpose"],
           ["LLM_BASE_URL", "http://localhost:8000/v1", "vLLM (or NIM) endpoint"],
           ["LLM_MODEL", "Llama-3_3-Nemotron-Super-49B-v1_5", "served model id"],
           ["ATLAS_COPILOT_DISABLED", "1", "hard-disable the legacy Copilot/Chrome engine"],
           ["TP_SIZE / MAX_MODEL_LEN", "2 / 8192", "tensor-parallel · context window"],
           ["POOL_SIZE", "4", "concurrent job workers"],
           ["guardrails_enabled", "false", "command-box input rail"],
           ["guardrails_strictness", "balanced", "lenient / balanced / strict"],
           ["guardrails_blocked_terms/_domains", "‘’", "command denylist / research source filter"],
           ["system_pin", "‘’", "6-digit PIN required for any delete"]],
          [2.9, 2.0, 2.5]))

# 17
sec("TROUBLESHOOTING",
    table([["Symptom", "Cause & Fix"],
           ["Model down / app errors on inference", "Run ./demo_health.sh; if red, ./demo_health.sh --recover (heals vLLM only if down). Check ~/vllm_service_manager.sh status."],
           ["400 'maximum context length' in logs", "Prompt + max_tokens exceeded 8K; complete() self-corrects and retries. Persistent → the input is too large; it is capped/map-reduced."],
           ["Raw <think> in a rationale/output", "max_tokens too small truncated the JSON before </think>; budgets were raised + a defensive strip added."],
           ["Guardrails blocked a legit command", "Lower strictness or clear blocked words in the panel; or toggle the master off (./guardrails.sh off). Fail-open means errors never block."],
           ["A block didn't show in the panel", "Blocks are a shared file (vault/guardrails_blocks.json); the panel auto-polls every 4 s — reload if needed."],
           ["DOCX convert produced few sites", "Best-effort: prose/blank tables don't map; edit the generated .xlsx in the Net editor and regenerate."],
           ["A delete asks for a PIN", "Set a 6-digit System PIN in Settings; deletes are PIN-guarded soft-deletes to recyclebin/."]],
          [2.4, 5.0]))


def build():
    doc = BaseDocTemplate(OUT, pagesize=LETTER,
                          leftMargin=0.8 * inch, rightMargin=0.8 * inch,
                          topMargin=0.85 * inch, bottomMargin=0.8 * inch,
                          title="ATP — Engineering Document", author="Manuel Zelaya")
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="main")
    doc.addPageTemplates([
        PageTemplate(id="first", frames=[frame], onPage=_first),
        PageTemplate(id="later", frames=[frame], onPage=_later),
    ])

    story = []
    story += [Spacer(1, 1.7 * inch),
              Paragraph("ATP", S["title"]),
              Paragraph("Account Technology Profiler", S["subtitle"]),
              Spacer(1, 8),
              Paragraph("Engineering Document", S["tpb"]),
              Spacer(1, 6),
              Paragraph("An autonomous, agentic operating system for a Solutions Architect", S["tag"]),
              Paragraph("Local NVIDIA Nemotron-Super-49B  |  vLLM · 2× H100 (TP=2)  |  Reasoning Brain + Multi-agent Brainwave  |  No API keys", S["tag"]),
              Spacer(1, 1.4 * inch),
              Paragraph("Manuel Zelaya", S["tpb"]),
              Paragraph("Solutions Architect", S["tp"]),
              Spacer(1, 6),
              Paragraph("Version 2.0  |  June 2026", S["tp"]),
              Paragraph("SHI International Corp.  |  Solutions Engineering", S["tp"]),
              Spacer(1, 24),
              Paragraph("CONFIDENTIAL", S["tpb"]),
              NextPageTemplate("later"), PageBreak()]

    def _toc_label(t):
        lbl = t.title()
        for a, b in (("Atp", "ATP"), ("Nemo", "NeMo"), ("Docx", "DOCX"), ("Sedraw", "SEdraw"),
                     ("Rag", "RAG"), ("Nim", "NIM"), ("Gpu", "GPU"), (" & ", " &amp; ")):
            lbl = lbl.replace(a, b)
        return lbl

    story.append(Paragraph("TABLE OF CONTENTS", S["h1"]))
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
