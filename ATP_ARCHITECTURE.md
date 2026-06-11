# ATP — Account Technology Profiler · System Architecture & Agentic Flow

**ATP (Account Technology Profiler)** is an autonomous, agentic operating system for a Solutions
Architect, running entirely on **local NVIDIA infrastructure**. It reads and reasons over a Solutions
Architect's accounts, builds and maintains a structured technology profile per customer, generates
deliverables (briefings, battlecards, network/vision diagrams), and runs a multi‑agent reasoning
**Brain** from a single command box — all powered by a **self‑hosted NVIDIA Nemotron‑Super‑49B model
served with vLLM across two H100 GPUs**, with **no external API keys, no cloud LLM, and no customer
data egress** (the one opt‑in exception is the live web‑research agent).

> This document is the master technical reference. Companion artifacts: `ATP_ARCHITECTURE.drawio`
> (one‑page diagram), `NEMOTRON_ARCHITECTURE.md` (model/serving deep‑dive), `ATP_Engineering_Document.pdf`
> (engineering deep‑dive), `ATP_User_Guide.pdf` (end‑user guide).

---

## 1. Heritage & the Copilot → Nemotron pivot

ATP began as **ATLAS** (Autonomous Tactical Learning Agentic System), whose inference substrate was
**Microsoft 365 Copilot driven through a browser** (Selenium + persistent Chrome profiles, a pool of
concurrent "agents"). That design avoided API keys but depended on a live, licensed, signed‑in Copilot
web session and an outbound browser.

ATP replaces that substrate wholesale with a **local, sovereign model**: `nvidia/Llama‑3_3‑Nemotron‑
Super‑49B‑v1_5`, served by **vLLM** (OpenAI‑compatible) on **2× NVIDIA H100 NVL** at tensor‑parallel = 2.
The Copilot/Chrome engine is hard‑disabled (`ATLAS_COPILOT_DISABLED=1`); the browser pool, the M365
calendar/meeting ingestion, and the Selenium agents are all retired. Everything the Brain and the skills
do now runs through one local inference client (`atlas/engine/nemotron.py`). The application code, the
job engine, the vault, the skill registry, and the agentic patterns were preserved and re‑grounded on
Nemotron.

**Why it matters for the demo:** the model is provably running on the two H100s (≈82 GB resident per
card — full tensor‑parallel shard), inference is local and private, and the same OpenAI‑compatible
client is **NIM‑ready** — pointing ATP at an NVIDIA NIM is a single environment variable.

---

## 2. Layered architecture

| Layer | Component | Role |
|---|---|---|
| 1 · UI | `run_atlas_linux.py` · `atlas/web/index.html` | Single‑page console served locally; opened as a Chrome **app‑mode** window. Pull model (polls jobs/artifacts). |
| 2 · API | `atlas/web/server.py` · `atlas/web/api.py` | `ThreadingHTTPServer` on `127.0.0.1:8080`; `POST /api/<method>` → `Api.<method>`; returns job ids / JSON. |
| 3 · Brain | `atlas/brain/nemotron_brain.py` · `jobs/manager._brain_route_nemotron` | Routes a free‑text command → run_skill / navigate / rag / research / brainwave, on Nemotron. |
| 4 · Jobs | `atlas/jobs/manager.py` | Worker pool; runs everything as cancellable background jobs; persistence + dependency chaining. |
| 5 · Engine | `atlas/engine/nemotron.py` · `websearch.py` | Local Nemotron client (streaming, cancellable, NIM‑ready) + live web search. |
| 6 · Guardrails | `atlas/brain/guardrails.py` + `guardrails_panel.py` | NeMo Guardrails input rail on the command box + standalone control panel. |
| 7 · Stores | `vault/` · `atlas/store/*` · `atlas/atp/*` | Customers, artifacts, ATP profiles, settings, soft‑delete recycle bin. |

**Request lifecycle:** UI `POST /api/command` → `Api.command()` → (guardrail `check_input`) → submit a
`brain_route` job → `JobManager` runs `_brain_route_nemotron` → Nemotron classifies intent → dispatches a
skill / RAG / research / brainwave job → result is rendered in the UI and filed as an artifact + a
Brainwave‑History reasoning receipt.

---

## 3. The Nemotron engine (`atlas/engine/nemotron.py`)

- **Endpoint, env‑driven (NIM‑ready):** `LLM_BASE_URL` (default `http://localhost:8000/v1`),
  `LLM_MODEL` (`Llama‑3_3‑Nemotron‑Super‑49B‑v1_5`), `LLM_API_KEY` (`dummy`; vLLM ignores it). The same
  OpenAI client points at local vLLM **or** an NVIDIA NIM with zero code change.
- **`complete(prompt, *, system="detailed thinking off", temperature=0.6, top_p=0.95, max_tokens=None,
  retries=2, on_log=None, should_cancel=None)`** — single stateless completion.
- **Nemotron quirks handled:** the model always emits a `<think>…</think>` reasoning block →
  `strip_think()` removes it; greedy (temp 0) loops, so NVIDIA's recommended **temp 0.6 / top_p 0.95**
  is used; the live `max_model_len` (8192) is read from `/v1/models` and used to budget `max_tokens`
  so prompt + reasoning + answer fit the window.
- **Cancellation (streaming abort):** when `should_cancel` is supplied, the request is **streamed** and
  the flag is polled between chunks; on cancel the stream is closed (vLLM stops generating → frees the
  GPU) and a `Cancelled` exception is raised. This is the local‑model analog of "closing the browser."
- **Context‑overflow self‑correction:** if vLLM rejects a request for exceeding 8192 tokens, the error
  reports the real prompt size; `complete()` parses it and retries with a correctly shrunk `max_tokens`.
- **8 K context cap:** FlashInfer's 32 K path needs a CUDA toolkit (`nvcc`) that isn't installed; the
  server runs with `VLLM_USE_FLASHINFER_SAMPLER=0` at `--max-model-len 8192`. Prompts are budgeted and,
  where needed, **map‑reduced** to fit (see ATP extract and saved‑data grounding).

---

## 4. The Brain (`atlas/brain/nemotron_brain.py` + `manager._brain_route_nemotron`)

The command box routes through one Nemotron classification call into five actions:

1. **run_skill** — launch a customer‑scoped skill (e.g. *"strategic briefing for Acme"*). The resolved
   skill job is dispatched; its deliverable lands in Artifacts.
2. **navigate** — an interactive skill (SEdraw network/vision, People Resources) → the Brain replies
   "open **Skills → …** and follow the prompts" rather than auto‑running.
3. **rag** — an intelligent question over the **Customer Vault** ("which customers use Palo Alto?",
   "does Acme use CrowdStrike?"). See §5.
4. **research** — external/web research with no specific customer ("research the latest Palo Alto
   firewalls") → the live web‑research agent. See §6.
5. **brainwave** — a product‑fit recommendation ("is Verkada a good fit for Acme?") → the multi‑agent
   fan‑out. See §7.

**Skill grounding without per‑skill rewrites.** The Copilot‑era skills (strategic_briefing, account_360,
battlecard, whitespace, follow_up, environment_topology) called an `ask()` that assumed M365 grounding.
On Nemotron, the job runner builds `ask` as **`nemotron.complete(saved_context(customer) + prompt)`** —
i.e. the customer's saved ATP profile + recent trip reports are prefixed onto the skill's own prompt, so
the existing skills produce real, grounded JSON/markdown/diagram output with **zero per‑skill changes**.

**Every interaction is a receipt.** `_log_brainwave` writes a Brainwave‑History entry — the decision
("decided **run_skill** → `strategic_briefing`"), the grounding ("routed on **local Nemotron**"), an
agent trace table (engine = `Nemotron‑49B (vLLM·2×H100)`), and a model‑generated rationale (the "why").
Receipts are **engine‑aware** — no Copilot/Chrome/Selenium wording in the local build.

---

## 5. Vault RAG (intelligent retrieval over customers)

`nemotron_brain.rag_answer(question, …)`:

1. **Scope + terms** — a quick Nemotron parse decides single / multiple / **all** customers and the
   search terms (e.g. "palo alto", "crowdstrike"), with a deterministic fallback. `resolve_customer`
   maps free‑text names to vault slugs.
2. **Deterministic retrieval (cheap, scales to all ~84 customers)** — per in‑scope customer it scans
   the ATP `data_library.json` (vendor/product/category/notes), `trip_reports/*.md` (line snippets),
   `overview.json`, the vision/network `*.xlsx` cell text, and that customer's filed artifacts —
   collecting `{customer, source, detail}` hits, bounded to fit the context window.
3. **Cited synthesis** — Nemotron writes a markdown answer that cites **where** each fact was found
   (which trip report / ATP entry / vision board / artifact). The synthesis prompt treats the `##
   <Customer>` header as the authoritative identity (so leftover real names inside content don't
   misattribute), and says plainly when nothing matched.

Cooperatively cancellable: the scan loop and synthesis honor `should_cancel`.

---

## 6. Live web research (`atlas/engine/websearch.py`)

A dependency‑light agent (httpx + lxml; no API key): `search()` queries **DuckDuckGo** (lite, then
html), unwraps redirect links, and drops results from **Guardrails‑blocked domains**; `fetch()` pulls
readable page text via lxml; `research_brief()` assembles a compact, numbered **SOURCES** block (top
results + the first few fetched pages). The Brain's `research` action and the brainwave's research agent
both call it. If egress is blocked, it returns empty and the agent **falls back to model knowledge**
with a logged note.

---

## 7. The multi‑agent Brainwave (`manager._brainwave_nemotron`)

The headline agentic pattern, faithful to the original design and re‑grounded on Nemotron. For *"is X a
good fit for customer Y?"*:

1. **Fan out two agents in parallel** (each a real job on its own pool worker → genuine concurrent
   inference batched on the H100s):
   - 🔎 **Web research agent** (`bw_research`) — live web research on the product (§6 + Nemotron synthesis).
   - 🗂 **Customer‑infrastructure agent** (`bw_cust_saved`) — Nemotron over the customer's saved data
     (ATP + trip reports, capped to fit 8 K).
2. **Merge** both into an ephemeral `wave.md`.
3. **🧬 Synthesis agent** — Nemotron writes a grounded verdict (Verdict / Where it fits / Risks /
   Recommended next step), citing the customer's real stack.
4. **🔎 Self‑check agent** — a separate Nemotron pass *fact‑checks the verdict against the evidence*,
   flagging any claim not supported by the customer's data or the research, with a confidence rating.
   This is the "the brain checks its own work" layer.
5. **Audit receipt** — a `brainwave` artifact records the parallel‑agent trace (engine, parallel marks,
   output sizes), the verdict, and the self‑check, into **Brainwave History**.

Cancelling the brainwave (the ✕ on its chip) recursively cancels the sub‑agents (§9) and cleans up the
in‑progress artifact. The M365 live‑tenant freshness agent from the Copilot era is dropped (no tenant).

---

## 8. Skills (`atlas/skills/`)

A registry of `Skill.run(ctx, ask, log) → SkillResult`. Skills still exist and run, but for the demo the
**Skills page shows only the interactive SEdraw tools** (Network Diagrams, Vision Boards). The rest
(strategic_briefing, account_360, battlecard, whitespace, follow_up, environment_topology, daily_briefing,
knowledge_drop, trip_report, find_resource, ask) are **hidden from the page but remain registered and
runnable** — the Brain dispatches them from the command box (e.g. the home‑page starter chips:
*"Create a strategic account briefing for a customer"*, *"Is a new technology a good fit for a customer?"*).
Hiding is a single `_HIDDEN_SKILLS` filter in `api.skills()`; nothing is deleted.

### SEdraw — diagram skills (`atlas/sedraw/`)
- **Network Diagrams** — an Excel intake (`network_input/*.xlsx`; sites → infrastructure categories with
  Qty×Model + connections) → `NetworkTopologyGenerator` → a multi‑site `.drawio` + a self‑contained
  diagrams.net viewer. Full in‑GUI editor; **Create New** blank template; per‑file **🗑 delete**.
- **📄 Convert from DOCX** — upload a Word intake; Nemotron reads paragraphs + tables and best‑effort
  maps them onto the 23 valid network categories → writes the intake `.xlsx` → generates the map. Runs
  as a cancellable job; the resulting `.xlsx` is editable and regenerable.
- **Vision Boards (Vision Studio)** — two free‑text boxes (current / future state) → Nemotron builds a
  combined current‑(top)/future‑(bottom) architecture `.drawio`, with history (load older sessions) and
  a full editor. Backend Excel files are hidden, named with customer + date; per‑session **🗑 delete**.

---

## 9. The job engine (`atlas/jobs/manager.py`)

- **`JobManager`** runs a `Job` queue on a pool of worker threads (`POOL_SIZE`, default 4 — preserved
  from the pool design; even with Copilot disabled the workers exist, so the brainwave facilitator can
  wait while its sub‑agents run concurrently). Jobs are mirrored to `vault/jobs.json` and survive restarts.
- **`submit(kind, ctx, …, parent=None)`** — every request is a job; `parent` links sub‑jobs into a tree.
- **Cancellation (the ✕ on a Working‑on chip)** — `cancel(jid)` is **recursive over the job tree**:
  it walks the job + all descendants and, for each, sets the per‑job `cancel` flag (polled by the
  streaming `nemotron.complete` to abort mid‑generation and free the GPU) and, for any legacy
  Chrome‑bound job, calls `request_stop()`. A cancelled brainwave stops its research/customer sub‑agents,
  skips synthesis/self‑check, and marks its artifact "⏹ cancelled."
- **Job kinds:** `brain_route`, `brainwave`, `bw_research`, `bw_cust_saved`, `web_research`,
  `docx_network`, `vision_generate`, `atp_generate`, the skill kinds, `finalize_receipt`, and the
  legacy gather/range kinds (disabled).

---

## 10. ATP — the customer technology profile (`atlas/atp/`)

- **`extract.generate_local(ask, customer, log)`** — **map‑reduce** over the customer's trip reports:
  chunk the text to fit 8 K, run TECH / OVERVIEW / CONTACTS prompts per chunk concurrently, then reduce
  (merge technologies, clean+merge contacts, synthesize the overview). This builds the profile on
  Nemotron with no browser.
- **`generations.py`** — every "✨ Generate" is archived as an immutable, timestamped snapshot
  (`account_technology_profile/generations/<id>/`) so a customer's profile drift is comparable over time.
  The live flat files are the editable working copy; **pin‑and‑merge** means hand‑edits win on regenerate.
  Per‑snapshot **🗑 delete** (the live "Current" is protected).
- **`data_library` / `profile_store` / `recency` / `topology_html`** — the structured technology
  inventory (vendor, product, category, deployment status, mention_count, last_seen), the overview +
  contacts stores, recency scoring, and the rendered topology HTML/diagram.

---

## 11. The Customer Vault & soft‑delete

`vault/customers/<slug>/` holds per customer: `trip_reports/`, `account_technology_profile/`
(+ `generations/`), `network_input|output/`, `vision_input|output/`, `artifacts/`. Customer display
names in the demo vault are **anonymized** (folder/display only).

**Non‑destructive deletes, PIN‑guarded.** Deleting a customer, an artifact, a vision board, a network
diagram, or a topology generation is a **soft‑delete to `vault/recyclebin/`** — the file(s) move out of
the live tree (so they vanish from the UI) but are never erased. Each delete is gated by the 6‑digit
**System PIN** (Settings); if no PIN is set, deletion is blocked with a prompt to set one. The frontend
uses one shared `pinDeleteModal`; the backend has matching PIN‑checked endpoints
(`delete_customer/artifact/generation`, `sedraw_vision_delete`, `sedraw_network_delete`).

---

## 12. NeMo Guardrails (`atlas/brain/guardrails.py` + `guardrails_config/`)

A **NeMo Guardrails input self‑check rail** on the command box, running on the **local Nemotron**.

- **OFF by default, fail‑open, native fallback** — gated on the `guardrails_enabled` setting. When off,
  `check_input()` is a no‑op (the app behaves identically). Any error → allow (never blocks legit work).
  Three‑tier evaluation: (1) deterministic **blocked‑words denylist** (instant); (2) real **NeMo
  Guardrails `LLMRails` `self_check_input`** rail (primary, on local Nemotron via OpenAI provider);
  (3) a **native Nemotron classifier** fallback if the package can't load.
- **Lever‑driven** (`settings.json`): master on/off, category toggles (keep on‑topic / block unsafe /
  block prompt‑injection), **strictness** (lenient/balanced/strict), **blocked words** (refuse commands
  containing them), and **blocked research domains** (the web agent skips them). Changing levers
  regenerates `guardrails_config/prompts.yml` and rebuilds the cached rail.
- **Wiring** — `Api.command()` calls `check_input` first; a block returns a refusal (no job spawned) and
  records to a **shared cross‑process block log** (`vault/guardrails_blocks.json`).
- **Config** — `guardrails_config/{config.yml, prompts.yml, rails.co}`; input self‑check only (no Colang
  dialog flows or embedding models → light, fully offline; a "detailed thinking off" instruction keeps
  the yes/no verdict clean).

### Guardrails Control Panel (`guardrails_panel.py`) — a separate process
A standalone stdlib web app on **`:8090`** (own process, its own Desktop shortcut). It reads/writes the
**same** `guardrails_*` settings the app reads — so it governs the live command‑box rail — but **cannot
crash ATP** (separate process). Levers (master + categories + strictness + blocked words + blocked
sources), a **live Test box** (ALLOW/REFUSE + reason + which engine ran), a **Recent blocks** log
(reads the shared file, auto‑refreshes every 4 s), and a **💾 Save** button.

---

## 13. Operations & scripts (all in `~/ATLAS/`)

- **`demo_health.sh`** — pre‑demo "all systems go" board: GPUs (2× H100), model weights resident on both
  cards (TP=2), vLLM `/health` + `/v1/models`, a **live generation round‑trip** (latency + tokens/s),
  and the ATP app — each with a green tag. `--recover` / `--restart` delegate to the vLLM manager;
  `--manage` opens its menu.
- **`guardrails.sh on|off|status`** — terminal toggle for the command‑box rail (takes effect on the
  next command; no restart).
- **`guardrails_panel.sh`** / **`launch_guardrails_panel.sh`** — launch the control panel (+ Desktop
  shortcut `Guardrails.desktop`).
- **`run_atlas_linux.py`** / **`launch_atlas_terminal.sh`** + `ATP.desktop` — the app launcher (Chrome
  app‑mode window; no Copilot/Chrome agents started).
- **`~/vllm_service_manager.sh`** — manages the vLLM server in a tmux session (`ai`): status / start /
  graceful stop / restart / quick‑recover / GPU topology / attach / tail logs. Config: TP=2,
  `--max-model-len 8192`, `--gpu-memory-utilization 0.85`, `--enforce-eager`, `VLLM_USE_FLASHINFER_SAMPLER=0`.

---

## 14. Security & data boundary

- **Sovereign, local inference.** The model runs on the user's own 2× H100s via vLLM. No API keys, no
  cloud LLM, **no customer‑data egress.**
- **One opt‑in network path.** The web‑research agent makes outbound DuckDuckGo/page requests — only the
  search query leaves the box, and only when the user runs research/brainwave. Domains can be denylisted.
- **PIN‑guarded, non‑destructive.** All deletes are soft‑deletes to `recyclebin/`, gated by the System PIN.
- **Guardrails.** The command box can be governed by the input rail (topical/safety/injection + denylists),
  with a full audit log of blocks.
- **NIM‑ready.** Swapping vLLM for an NVIDIA NIM (or a hosted NIM) is one env var (`LLM_BASE_URL`).

---

## 15. File map

```
~/ATLAS/
  run_atlas_linux.py                  app launcher (ATLAS_COPILOT_DISABLED=1)
  config.py                           vault dirs, POOL_SIZE, RECYCLEBIN_DIR, …
  atlas/
    web/      server.py · api.py · index.html
    brain/    nemotron_brain.py · guardrails.py · guardrails_config/ ·
              brainwave.py · capabilities.py · rules.py · router.py (legacy)
    engine/   nemotron.py · websearch.py · pool.py · copilot.py (disabled)
    jobs/     manager.py · scheduler.py
    skills/   base.py + skills · peopleresources/
    sedraw/   network_*.py · drawio_generator.py · vision_ai.py · docx_to_network.py · service.py
    atp/      extract · generations · recency · topology_html · data_library · profile_store
    store/    vault · customers · artifacts · settings · cron · people
  guardrails_panel.py                 standalone Guardrails Control Panel (:8090)
  demo_health.sh · guardrails.sh · guardrails_panel.sh · launch_*.sh
  ATP_ARCHITECTURE.md / .drawio        this reference + one-page diagram
  GUARDRAILS_ARCHITECTURE.drawio       guardrails integration diagram
  NEMOTRON_ARCHITECTURE.md             model/serving deep-dive
  ATP_Engineering_Document.pdf · ATP_User_Guide.pdf
  vault/                               all runtime data + recyclebin/ + guardrails_blocks.json
~/vllm_service_manager.sh             vLLM lifecycle manager (tmux 'ai')
```

---

## 16. Configuration reference

| Setting / env | Where | Default | Purpose |
|---|---|---|---|
| `LLM_BASE_URL` | env / `nemotron.py` | `http://localhost:8000/v1` | vLLM (or NIM) endpoint |
| `LLM_MODEL` | env | `Llama-3_3-Nemotron-Super-49B-v1_5` | served model id |
| `ATLAS_COPILOT_DISABLED` | env | `1` | hard‑disable the legacy Copilot/Chrome engine |
| `MAX_MODEL_LEN` | vllm_service_manager.sh | `8192` | context window |
| `TP_SIZE` | vllm_service_manager.sh | `2` | tensor‑parallel across 2× H100 |
| `POOL_SIZE` | config.py | `4` | concurrent job workers |
| `guardrails_enabled` | settings.json | `false` | command‑box input rail |
| `guardrails_strictness` | settings.json | `balanced` | lenient / balanced / strict |
| `guardrails_blocked_terms` / `_domains` | settings.json | `""` | command denylist / research source filter |
| `system_pin` | settings.json | `""` | 6‑digit PIN required for any delete |

*ATP — Account Technology Profiler · local NVIDIA Nemotron‑Super‑49B on 2× H100 (vLLM, TP=2) · agentic
Brain + multi‑agent Brainwave + vault RAG + live web research + NeMo Guardrails · fully local, no API keys.*
