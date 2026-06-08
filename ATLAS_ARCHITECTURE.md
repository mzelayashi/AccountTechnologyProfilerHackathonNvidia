# ATLAS — Master Architecture
### A.T.L.A.S. — Autonomous Tactical Learning Agentic System

> The single reference for the **entire** ATLAS program — how it runs, every page and section, the
> Brain, the jobs/engine, the stores, ATP, Cron, and how it all fits together. Companion diagram:
> `ATLAS_ARCHITECTURE.drawio` (one-page, traces the agentic flow). Companion data the Brain reads:
> `atlas/brain/capabilities.py` (capability manifest) and `vault/brain/brain_rules.md` (editable rules).

---

## 1. What ATLAS is & guiding principles

ATLAS — **Autonomous Tactical Learning Agentic System** — is an operating system for a Solutions
Architect. It pairs an **ontology-driven operating picture** (every customer, meeting, technology,
contact, and deliverable is a typed object linked into one navigable model) with an **autonomous
reasoning agent** (from one command box it interprets intent, decomposes a goal, dispatches parallel
work, and synthesizes the result). Its inference substrate is **Microsoft 365 Copilot driven through a
real browser** (Selenium + Edge/Chrome profiles) — **no API keys, no tokens, no admin scopes**.
Whatever Copilot can see for the signed-in user, ATLAS can orchestrate.

- **Browser-as-brain.** Copilot is the LLM; ATLAS runs *threads* of it in **Work** mode (M365 tenant
  grounding — calendar, transcripts, emails, files) or **Web** mode (public, faster, no tenant link).
- **Everything is an artifact.** Every deliverable and conversation is logged, readable in-app,
  content-searchable, and transferable. Trip reports are first-class artifacts.
- **Non-destructive.** Deletes are PIN-guarded **soft-deletes** to `vault/recyclebin/`, never hard
  deletes. Regeneration **never clobbers hand-edits** ("edits win" pin-and-merge).
- **Concurrent & resilient.** All real work runs as background **jobs** on a pool of Chrome
  instances; jobs survive navigation and app restarts (`vault/jobs.json`).
- **Self-aware.** The Brain knows its own capabilities (the manifest) and rules, so it can say *"I can
  do that,"* *"I can't yet — here's the skill to add,"* or *"I can't change that setting — go here."*

---

## 2. Run model

```
atlas_web.py  (launcher)
  ├─ artifacts.backfill_trip_reports()   # every trip-report .md becomes an artifact
  ├─ Api()                               # the facade the UI calls
  ├─ ThreadingHTTPServer 127.0.0.1:<port> serving atlas/web/server.py
  ├─ scheduler.start_scheduler()         # Cron Jobs daemon
  ├─ scheduler.start_calendar_autorefresh()   # re-gather the 3 days every 30 min
  └─ webview.create_window(...) → WebView2 (Edge) renders atlas/web/index.html
```

The UI is a **single HTML page** that talks to Python over a tiny HTTP bridge:
`fetch POST /api/<method>` with a JSON body → `Api.<method>(**body)` → JSON back. It's a **pull
model**: the page polls `jobs()`, `days()`, `artifacts()`, `suggestions()` every ~1.5 s and re-renders.
Long work never blocks the UI — it's a job on the engine pool. The server sends **`Cache-Control:
no-store`** on every response so a relaunch always loads fresh UI (no stale `index.html` in WebView2).

---

## 3. The Home console

Three columns under a **Working on** job bar (live spinner chips for active jobs, ✓/⚠ for finished).
Each **active** chip carries an **✕** that cancels the job and closes the Chrome it's using (§6). The
center column is **scrollable** when content is tall.

- **Left — Calendar.** Yesterday / Today / Tomorrow toggle, with a **↻ refresh** button to re-gather the
  selected day on demand (`refresh_day` — Copilot's calendar grounding is occasionally flaky). On boot,
  three `gather_day` jobs gather each day's meetings (cached to `vault/daily/<date>/`), and a daemon
  **auto-refreshes all three every 30 min** (`calendar_autorefresh_min`). Meeting cards → **meeting
  detail** → for a past meeting, **📝 Create Trip Report** (passes that meeting's *calendar date*, not
  today's).
- **Center — the command cluster** (top-aligned), in order:
  - a row of **five quick-nav buttons** — Customer Vault · People Resources · Cron Jobs · Skills · Artifacts.
  - the animated **orb** (pulsing glow ring) — the brain.
  - **🧠 Brainwave History** button · greeting · **date · live time**.
  - the **command box** — a roomy **3-row textarea** ("Ask ATLAS to do anything"; Enter sends,
    Shift+Enter = newline) → the Brain (§5).
  - **💡 Continual Suggestions** (§5a) — the proactive next-best-action panel, with a *Suggest now*
    button, pinned directly above the scheduled-jobs strip.
  - **Today's Scheduled Jobs** — a small glass card at the **bottom** listing the crons that fire today
    with their times and a ✓ done badge; hidden when none.
- **Right — Recent Artifacts.** Timestamp-sorted (newest first; future-dated items clamped down;
  **brainwaves excluded** — they live in Brainwave History). "open all →" opens the Artifacts browser.

---

## 4. Sections & views (the whole UI)

Top bar: **Home · ⚙ Settings · About** (the Customer Vault / People Resources / Cron Jobs / Skills /
Artifacts shortcuts now live as the five buttons in the Home command cluster).

| Section / view | What it does |
|---|---|
| **Home** | The console above. |
| **Artifacts** browser | All deliverables/conversations (brainwaves excluded). 🔎 content search (title/customer/text) + **📥 Unfiled only** toggle (no customer tag) for sweeping & filing. Each: open & read (rendered markdown), **📁 File to customer** (file *or transfer* between customers), ✉️ Email (trip reports), 🗑 PIN-guarded delete. |
| **Customer Vault** | Searchable grid of customers. Create customer. A customer page shows Trip Reports / ATP / Network Diagrams / Artifacts, an **Overview** + **Key Contacts** panel, a **📅 Generations** picker, and buttons: **🧩 Edit Technology Profile** (the ATP editor), **🛰 Topology**, **✨ Generate from trip reports**, **🗑 Delete customer** (PIN). Clicking a trip report opens its in-app artifact view. |
| **ATP editor / Topology** | Edit the live technology profile (4 categories, add/edit/delete, pin-and-merge); render the glowing 10-column topology where each tech shows *appears in N trip reports* + *last seen*. |
| **Cron Jobs** | Create a scheduled instruction: free text + time + **Daily/Weekly/Monthly** (weekly → weekday checkboxes, monthly → day-of-month). List with human schedule, next-run, enable/disable, delete. |
| **🧠 Brainwave History** | Browse every brain-console interaction (agentic outputs). Click to read; 🗑 to delete (PIN). Brainwaves are *multifaceted* — not filed to one customer. |
| **⚙ Settings** | Trip-report recipients, email signature, auto-email, **🌍 Timezone** (cron), **🔒 System PIN** (required for any delete), **🧠 Brain Rules** editor (train the Brain), **Show Chrome windows** (debug — off = hidden/minimized), fan-out knobs (`gather_window_size`, `batch_concurrency`, `calendar_autorefresh_min`), and a **💡 Continual Advice** group (`continual_suggestions`, `suggestions_ai`, `suggestions_frequency_min`, `suggestions_focus_customer`, `suggestions_workhours_only`). |
| **Skills** | Grid of the 12 registered skills; pick one, fill its input form → run it **directly** (no routing). |
| **🧑‍💼 People Resources** | Browse/edit the SHI resource directory (engineers, vendors, assessments, tools) — `resources.csv` is the editable **source of truth**. Category chips + live filter (name/specialty/region/practice). PIN-gated **add/edit/delete**; **⬇ Import** a new CSV (archives the prior one, never destroys). The `find_resource` brain skill answers *"a TOLA expert who can do PAM or EDR."* |
| **Job detail** | Live log + result for any job; auto-follows a Brain job to the work it spawned. |
| **Chat** | Resume a saved Copilot conversation (an "ask" artifact) on its own Chrome thread and append turns. |

---

## 5. The Brain (orchestration)

The command box is a **reasoning router**, not keyword matching.

```
command(text)
  → JobManager.submit("brain_route", {text}, mode="web")
  → _brain_route():
       fast-path is_meta?                   → answer about ATLAS from the manifest
       fast-path meeting_trip_reports_day?  → trip_reports_day (one trip_report per meeting of a day)
       else router.classify(ask_web, text)  # Copilot-WEB, grounded on the capability manifest
            → { action, skill, ctx, items[], collection, explanation, ... }
       act on the decision  →  log the interaction to Brainwave History
```

| decision | behavior |
|---|---|
| `capabilities` | answer "what can you do / your skills" from `capabilities.human_summary()`. |
| `run_skill` | spawn the matched skill with extracted `ctx` (the **deliverable** lands in Artifacts). |
| `plan` | **decompose** a multi-target goal into N **parallel** skill runs (see below). |
| `brainwave` | spawn the multi-agent fan-out below. |
| `settings` | return the exact pointer; ATLAS never changes its own settings. |
| `cannot_do` | research why + recommend a skill to add (the `planned` manifest entries seed this). |

**The planner (decomposition — "another layer of thought").** A skill acts on ONE target (one
account, one meeting). So when you ask for a skill across **multiple** targets, the Brain *reasons*
about it and returns `action=plan` with the per-item `skill` and either explicit **`items`** (named
targets) or a **`collection`** to resolve at runtime (`yesterday_meetings` / `today_meetings` /
`tomorrow_meetings` / `customers` / **`date_range`**). `_run_plan` then **fans out one skill job per
target in parallel** (the pool runs `POOL_SIZE`=7 at a time, capped at 15/plan), each producing its own
**artifact**, and logs one parent **Plan** entry to Brainwave History. Examples: *"battlecards for AWC,
ProPetro and Sendero"* → 3 parallel `battlecard` jobs; *"battlecard for AWC"* stays a single
`run_skill` — the Brain only decomposes when there's genuinely more than one target.

**Time reasoning + the date-range coordinator (`skill_over_range`).** The classifier is grounded with
**today's absolute date**, so it resolves any time expression ("May 21 to June 5", "last two weeks",
"yesterday") into **absolute ISO dates** (never Copilot's drifting "today") and returns
`collection=date_range` with `range:{start,end}` and an optional `filter:"external_customer"`. The
`skill_over_range` coordinator job then:
1. splits the range into ~5-day **windows** (`atlas/brain/timespan.py`) and gathers each **in parallel**
   on its own Chrome via `gather_window` (Copilot **Work** → the Graph calendar) — the user's "five days
   at a time, separate instances";
2. de-dupes + drops obvious non-meetings (a *conservative* skip-list — lunch/admin/1:1/OOO/standup, **not**
   ambiguous words like "sync"), then optionally runs a Copilot-**Web** reasoning pass to keep only
   **external customer** meetings;
3. **reduces to the chosen skill's granularity** — a *meeting* skill (`trip_report`, `meeting_prep`)
   fans out one job per meeting (dated to that meeting); an *account* skill (`strategic_briefing`,
   `battlecard`, …) reduces the calls to **distinct customers** (Web pass, snapped to canonical vault
   names) and fans out one job per customer;
4. fans out via `_fan_out(skill, items)` with a **sliding-window `after[]` throttle** so only
   `batch_concurrency` (default **4**) render at once — bounding RAM — capped at 40/job.
So *"trip reports for all my meetings May 21–June 5, external customers only"* and *"strategic
briefings for any external customer calls last week"* both work — **any** skill over a span, at its
natural granularity. (A dependency-release bug was fixed here too: `_is_settled` releases waiters on any
terminal state — done **or** error — so one failed report can't deadlock the throttle window.)

**Main prompt vs. running a Skill directly.** The main prompt *infers intent + parameters* and can
escalate to a brainwave or multi-step work; the Skills grid is you choosing the tool and filling its
form (deterministic, one shot, no routing). Same engine underneath — the difference is everything *in
front of* the engine call.

**The brainwave (the agentic core).** For *"is &lt;product&gt; a good fit for &lt;customer&gt;?"* —
`_brainwave` creates a **Brainwave History entry immediately** (survives interruption), grounds on the
customer's **own saved data** (Brain Rule #1), then fans out **3 parallel sub-agents**:

| # | agent | mode | reads |
|---|---|---|---|
| 1 | 🗂 saved data | Web | the customer's actual trip-report content + ATP (chunk-fed so *all* reports are read) |
| 1 | 🔎 research | Web | public product research |
| 1 | 🏢 live check | Work | M365 freshness/redundancy not in filed notes |
| 2 | 🧬 synthesis | Web | merges all three (`wave.md`) → a grounded verdict |

The entry is then **filled in** with the verdict + a trace table (which agent/instance did what).
**Every** brain-console command logs to **Brainwave History** as a complete **🧠 Reasoning receipt** so
you can judge the caliber of each interaction. The receipt *always* carries the **brain logic** (what was
decided + why, and that classification ran on Copilot Web), and — once the spawned work settles — a
**`finalize_receipt`** job (gated on those jobs via `after=`, so it never blocks a pool worker) enriches
it with the **agent trace** (each agent/skill · Copilot **Work/Web** mode · **Chrome instance** ·
output), a **rationale / logic of the answer** (for a single deliverable, a Copilot-Web pass explaining
*why* — e.g. why a chosen resource fits), and the **technology used** (Copilot via the browser pool, how
many Chrome instances). Childless answers (capabilities/settings/cannot_do) read *"answered from the
manifest — 0 Chrome instances."* The deliverables themselves go to **Artifacts**.

- **Capability manifest** — `atlas/brain/capabilities.py`: skills auto-derived from the live registry
  + engine/vault/ATP/settings-pointer/planned entries. The Brain's introspection source.
- **Capability manifest** & **Brain Rules** (above) are the Brain's introspection + constitution.

### 5a. Continual Suggestions (the proactive layer) — `atlas/brain/suggest.py`

Because ATLAS stays open all day with idle agents and full calendar awareness, the Home screen shows a
calm **next-best-action** panel (above the scheduled-jobs strip). It only *suggests*; nothing runs until
you tap a chip (which fires it as a normal, visible job). **Two tiers:**

- **Tier 1 — instant (free, no Copilot):** rule-based chips from local signals — the **next meeting** +
  its customer (`meeting_prep`, `strategic_briefing`), the **focus customer**, a **recent trip-report**
  customer (follow-up), and morning → daily briefing. Computed fresh on every poll.
- **Tier 2 — strategic (Copilot-Web, throttled):** a **`suggest`** job reads the customer's saved data
  (`customer_saved_text`) and returns up to 3 specific plays (`LABEL :: COMMAND`), cached to
  `vault/brain/suggestions.json`. Refresh is **event-driven** (a `context_key` of focus-customer or
  next-meeting changes) **+ a frequency floor** (default 60 min), gated by work-hours and the AI toggle.

`Api.suggestions()` serves Tier-1 fresh + Tier-2 cached (cached items display whenever recent, ≤6 h —
context drift never hides them); it debounce-submits the `suggest` job when due. `Api.request_suggestions()`
is the **Suggest now** button — forces a run immediately, bypassing the floor / work-hours / AI gate.
Every run (manual or auto) leaves a **"Suggestions — …"** record in Brainwave History and shows on the
loader. Tiles show a clear label, a faint command preview, and the full command on hover. Five settings
govern it (see §4). Guardrails: max 4, dismissible, grounded, suggest-not-act, throttled.

---

## 6. Jobs & concurrency

`atlas/jobs/manager.py` — `JobManager`:
- One **worker thread per Chrome slot**; `POOL_SIZE = 7` ⇒ up to 7 concurrent Copilot instances.
- `submit(kind, ctx, title, after=, icon=, mode=)` → a `Job{kind, ctx, mode(work|web), status, after[],
  session_idx, log, result}`. `after=` chains jobs; dependents are released on any **terminal** state
  (`_is_settled` = done/error/interrupted), so a failed dependency never deadlocks its waiters — this is
  what makes the date-range **sliding-window throttle** safe. Persisted to `vault/jobs.json` (survives
  restart; in-flight → "interrupted"). Idle Chrome auto-closes after 10 s.
- **Cancel (✕ on a Working-on chip)** — `JobManager.cancel(jid)`: a queued/waiting job is dropped before
  it runs; a **running** job is stopped by calling `Session.request_stop()` on its Chrome instance (a
  per-session stop signal the engine's wait loops honor, §7) so the worker unwinds promptly and the job
  ends **interrupted** — and the Chrome it was driving is force-closed. The pool reopens a fresh instance
  on the next job. Exposed as `Api.cancel_job(id)`.
- **Job kinds:** `gather_day`, the skills, `atp_generate`, `brain_route`, `brainwave`,
  `bw_research` / `bw_cust_saved` / `bw_cust_live`, `trip_reports_day`, **`skill_over_range`**
  (date-range coordinator), **`gather_window`** (parallel calendar gather for one window),
  **`finalize_receipt`** (enriches a Brainwave-History receipt with the agent trace + rationale after its
  child jobs settle), **`suggest`** (Tier-2 Continual Suggestions, §5a), `chat_continue`. A **plan**
  decision fans out N ordinary skill jobs (one per
  target) — that's how the
  Brain scales to the work — and `skill_over_range` does the same, throttled to `batch_concurrency` at
  once via a sliding-window `after[]` chain.

---

## 7. Engine

`atlas/engine/{pool,copilot}.py`:
- `EnginePool` clones `chrome_profile_0..6` from a signed-in seed; one `Session` each, per-session lock.
- **Hidden by default.** Each Chrome launches **off-screen** (`--window-position=-32000,-32000`) and is
  **minimized before it loads**, so the pool never flashes windows on screen. A real (non-headless)
  window is kept on purpose — long prompts paste via the clipboard and the sign-in path surfaces the
  window when M365 needs a login. Settings → **"Show the Copilot Chrome windows"** (`show_chrome_windows`,
  default off) flips them back on-screen for debugging.
- **Session primitives:** `ask` (one turn) · `ask_chain` (multi-turn, one thread) · `ask_chain_all`
  (every turn's answer — chunked feeds) · `ask_at(url, prompt)` (resume a saved thread).
- **Work|Web** toggle per call. **Completion** = the `ATLAS-RESPONSE-COMPLETE` marker (primary) +
  `accept` predicates (`substantial` >400, `brief` >80, `feed_or_substantial`) so Web answers finish
  without the marker. **Echo guard:** `_best_answer` drops any block containing `_ECHO_SIG`
  ("please add this line at the very end") so an echoed pasted prompt is never captured as the answer.
- **Long context** clipboard-pasted (>2000 chars). After an answer, M365 rewrites the URL to
  `/chat/conversation/<id>` (`current_url(wait_conversation=True)`) — captured for resume.
- **Cancellable** — each `Session` has a `threading.Event` stop signal; the box-find and answer-wait
  loops check it and bail. `Session.request_stop()` (called from another thread when a job is ✕'d, §6)
  sets it and force-closes this session's Chrome (`_kill_profile_chrome`, scoped to its own profile), so
  an in-flight turn ends at once; the session self-heals (reopens) on the next job.

---

## 8. Stores & data layout

```
vault/
  customers/<slug>/
    trip_reports/*.md                         # MHT-format reports (each is an artifact)
    account_technology_profile/
      data_library.json overview.json contacts.json topology.html
      generations/<YYYYMMDD-HHMMSS>/...        # immutable ATP snapshots
    network_diagrams/   artifacts/   customer.json
  artifacts.json        # the artifact log (deliverables + conversations + brainwaves)
  artifacts.json.corrupt-<UTC>   # auto-backup written if a corrupt file is ever recovered
  jobs.json             # job history (status bar)
  settings.json         # recipients, signature, auto-email, timezone, system_pin, show_chrome_windows,
                        #   gather_window_size, batch_concurrency, calendar_autorefresh_min,
                        #   continual_suggestions + suggestions_*
  cron.json             # scheduled instructions
  brain/
    brain_rules.md      # the editable Brain constitution
    brainwaves/<id>/wave.md   # per-brainwave merged context
    suggestions.json    # Continual Suggestions cache (Tier-2: {context, ts, items})
  recyclebin/           # soft-deleted customers + artifacts (never auto-purged)
  daily/<date>/briefing.json   # cached gathered meetings   ·  exports/  ·  inbox/
```

Stores (`atlas/store`): **vault** (slug/paths), **customers** (create/list/detail/`assign_artifact`
[file *or transfer*]/`delete_customer`→recyclebin), **artifacts** (`add`, `list_summaries`
[brainwaves excluded], `list_brainwaves`, `search`, `get`, `backfill_trip_reports`, `delete`→recyclebin,
`uri_id_map`), **settings**, **cron**. Soft-delete + PIN are enforced in the `Api`.

**People Resources store** (`atlas/store/people.py`): a CSV-backed directory at
`atlas/skills/peopleresources/resources.csv` (the permanent source of truth; migrated once from the
original `.xlsx`). `load/add/update/delete/search`, plus `import_csv` which archives the prior file to
`…/archive/` (drop a new CSV in `…/import/` → Import in-app). Read by both the `find_resource` skill and
the People Resources view; edits are PIN-gated in the `Api`.

**Concurrency-safe writes.** The pool runs many worker threads that write `artifacts.json` at once, so
the store does an **atomic write** (temp file → `os.replace`) under a **module lock** around every
load→mutate→save (`add`/`update`/`delete`/`backfill`). `_load` is **self-healing**: on a corrupt file it
backs up to `artifacts.json.corrupt-<UTC>`, **salvages** every intact record (brace-match + de-dupe by
id), rewrites a clean file, and **never silently returns `[]`** for populated-but-broken data. (This is
the template for the other JSON stores if they ever see the same write pressure.)

---

## 9. ATP subsystem (`atlas/atp`)

- **Generate** (`extract.generate`, Web): chunk all trip reports (~20K/turn, one conversation) → extract
  **technologies → topology**, a 3-paragraph **overview**, and **key contacts**; **pin-and-merge** keeps
  hand-edits; saved as a **timestamped generation**.
- **Relevancy** (`recency.py`): each tech shows *appears in N trip reports* + *last seen*, computed
  deterministically from report dates.
- **Topology** (`topology_html.py`): 10 glowing category columns, status-colored, click-for-specs.
- **Storage:** `data_library.py`, `profile_store.py`, `generations.py`.

---

## 10. Cron scheduler & calendar auto-refresh (`atlas/jobs/scheduler.py`)

**Cron** — a daemon (started in `atlas_web.main`) ticks every ~30 s, computes `now` in the **Settings
timezone**, and fires any **due** cron (`now ≥ today@HH:MM`, day matches daily/weekly/monthly,
`last_fired ≠ today`) by submitting a `brain_route` job with the instruction — *exactly as if you typed
it* (so a cron gets the full Brain: planning, date ranges, brainwaves). E.g. *"trip reports for each of
yesterday's meetings"* → `trip_reports_day` → one `trip_report` per past meeting. Runs while ATLAS is
open (same-day catch-up); `vault/cron.json` is the source of truth.

**Calendar auto-refresh** — a second daemon (`start_calendar_autorefresh`) re-gathers
yesterday/today/tomorrow every `calendar_autorefresh_min` minutes (default 30; 0 = off), recomputing the
dates each cycle so it rolls over at midnight. Calendars change through the day, and Copilot's grounding
is occasionally flaky — `gather_day` is hardened to **detect a calendar-refusal** ("I can't access your
calendar…") and the echoed format template, so a refusal retries once and then keeps the last good
briefing instead of writing a bogus "meeting title" card.

---

## 11. The agentic flow, end to end

> You type **"is Verkada a good fit for ProPetro?"**

1. `command()` → a `brain_route` job (Web). The router classifies it → `action=brainwave
   {product:"Verkada", customer:"ProPetro"}`.
2. A **Brainwave History entry** is created immediately ("🧠 running…").
3. The `brainwave` job grounds on ProPetro's saved data, then **fans out 3 jobs in parallel** across
   the pool: 🗂 saved-data (Web, all filed reports) ‖ 🔎 Verkada research (Web) ‖ 🏢 live tenant check
   (Work).
4. Outputs merge into `vault/brain/brainwaves/<id>/wave.md`; 🧬 synthesis produces a grounded verdict.
5. The history entry is **filled in** with the verdict + an orchestration trace (which Chrome instance
   ran which agent). If it had created a deliverable (e.g. a trip report), that lands in **Artifacts**.

Same path for a simpler command — e.g. *"create a trip report for yesterday's Virtuix sync"* routes to
the `trip_report` skill (deliverable → Artifacts) and logs the interaction to Brainwave History. And a
**multi-target** command — e.g. *"battlecards for AWC, ProPetro and Sendero"* — is **decomposed** by the
planner into 3 parallel `battlecard` jobs (the engine pool runs them 7-at-a-time) → 3 artifacts, with
one Plan entry in Brainwave History.

A **date-range** command — *"strategic briefings for any external customer calls from May 21 to June
5"* — resolves the span to absolute dates, runs `skill_over_range`: ~4 parallel `gather_window` jobs
read the Graph calendar, the meetings are filtered to external customers, **reduced to the distinct
customers**, and one `strategic_briefing` per customer is fanned out **4 at a time** — each a dated
artifact, with one Plan receipt in Brainwave History.

---

## 12. File index

| Area | Files |
|---|---|
| Launcher / shell | `atlas_web.py`, `atlas/web/server.py`, `atlas/web/index.html` |
| API facade | `atlas/web/api.py` (~42 methods, incl. `suggestions`/`request_suggestions`, `refresh_day`, `cancel_job`) |
| **Brain** | `atlas/brain/capabilities.py` (manifest), `router.py` (classify/fast-paths/time-grounded), `brainwave.py` (fan-out), `rules.py` (constitution), `timespan.py` (date-range math), `suggest.py` (Continual Suggestions) |
| Orchestrator (fallback) | `atlas/orchestrator/router.py` (keyword router, used only if the Brain fails) |
| Jobs / scheduler | `atlas/jobs/manager.py` (pool, `cancel`), `atlas/jobs/scheduler.py` (cron + calendar auto-refresh) |
| Engine | `atlas/engine/copilot.py`, `atlas/engine/pool.py` |
| Skills | `atlas/skills/*.py` (`base.py` = framework; 12 skills), `atlas/skills/peopleresources/` (`find_resource` + `resources.csv`) |
| Stores | `atlas/store/{vault,customers,artifacts,settings,cron,people}.py` |
| ATP | `atlas/atp/{extract,generations,recency,topology_html,data_library,profile_store}.py` |
| Config | `config.py` (`POOL_SIZE=7`, vault dirs, `RECYCLEBIN_DIR`, `CRON_PATH`); settings add `gather_window_size`, `batch_concurrency`, `show_chrome_windows`, `continual_suggestions` + `suggestions_*` |
| Diagram | `ATLAS_ARCHITECTURE.drawio` (one-page agentic map) |

*Kept in lock-step with the code. The capability manifest auto-derives from the live skill registry;
the Brain Rules are user-editable.*
