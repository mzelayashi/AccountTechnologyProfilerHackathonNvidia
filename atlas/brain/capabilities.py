"""The ATLAS capability manifest — what the platform can (and cannot) do, as data.

This is the single source of truth the Brain (and the UI) introspect. Skill entries are
**auto-derived** from the live skill registry so they never drift; everything else (engine
primitives, vault/artifact/ATP actions, settings pointers, and planned-but-not-built skills) is
hand-authored and mapped to the real `Api` method that performs it.

Each capability is a dict:
    id              short stable id
    kind            skill | engine | vault | atp | artifact | settings-pointer | planned
    title           human label
    description     one line: what it does / when the Brain should pick it
    invoke          how the Brain performs it — usually an Api method name, e.g. "run_skill(key=...)"
    engine_mode     "work" (M365 tenant grounding) | "web" (public) | "" (no Copilot)
    inputs          [field keys] the action needs
    can_do          True if ATLAS can do it today; False for settings-pointer / planned
    settings_location  for settings-pointer: where the user must go (ATLAS cannot self-modify settings)
    recommend       for planned: what skill should be added to enable it
"""
from __future__ import annotations


def _cap(id, kind, title, description, *, invoke="", engine_mode="", inputs=None,
         can_do=True, settings_location="", recommend="") -> dict:
    return {"id": id, "kind": kind, "title": title, "description": description,
            "invoke": invoke, "engine_mode": engine_mode, "inputs": list(inputs or []),
            "can_do": can_do, "settings_location": settings_location, "recommend": recommend}


def _skill_caps() -> list[dict]:
    """Auto-derived from the live registry — the Brain's 'run a built-in skill' tools."""
    from atlas.skills import all_skills
    out = []
    for s in all_skills():
        out.append(_cap(
            s.key, "skill", s.name, s.description,
            invoke=f"run_skill(key='{s.key}', ctx={{{', '.join(f.key for f in s.inputs)}}})",
            engine_mode="work",                       # all skills ground on the M365 tenant
            inputs=[f.key for f in s.inputs]))
    return out


# --- engine primitives: the raw agent building blocks the Brain composes -------------------------
_ENGINE = [
    _cap("engine.ask", "engine", "Single Copilot turn",
         "One prompt → one answer, fresh thread.", invoke="Session.ask(prompt, mode=)",
         engine_mode="work|web"),
    _cap("engine.ask_chain", "engine", "Multi-turn (one thread)",
         "Several prompts in ONE conversation, accumulating context; returns the last good answer.",
         invoke="Session.ask_chain(prompts, mode=)", engine_mode="work|web"),
    _cap("engine.ask_chain_all", "engine", "Multi-turn, all answers",
         "Like ask_chain but returns every turn's answer (chunked feed + multiple extractions).",
         invoke="Session.ask_chain_all(prompts, mode=)", engine_mode="work|web"),
    _cap("engine.ask_at", "engine", "Resume a saved thread",
         "Navigate to a saved /chat/conversation/<id> URL and ask a follow-up — folds context into "
         "the parent brainwave thread.", invoke="Session.ask_at(url, prompt, mode=)",
         engine_mode="work|web"),
    _cap("engine.fanout", "engine", "Parallel fan-out",
         "Run up to POOL_SIZE Copilot Chrome instances at once (work + web mixed) as background jobs "
         "with dependency chaining.", invoke="JobManager.submit(kind, ctx, mode=, after=)"),
    _cap("brain.brainwave", "engine", "Brainwave — product fit for a customer",
         "Evaluate/research a product or technology for a named customer: fans out a Web product-"
         "research agent ‖ a Work customer-analysis agent (grounded in the customer's ATP profile + "
         "trip reports), merges them, and synthesizes a grounded verdict saved as a brainwave artifact.",
         invoke="command('is <product> a good fit for <customer>?')", engine_mode="web+work"),
]

# --- vault / customers / artifacts: the Brain's retrieval + filing tools --------------------------
_VAULT = [
    _cap("vault.customers", "vault", "List / search customers",
         "Enumerate customer folders in the vault.", invoke="customers()"),
    _cap("vault.create_customer", "vault", "Create a customer",
         "Make a new customer folder tree.", invoke="create_customer(name)"),
    _cap("vault.customer", "vault", "Open a customer",
         "Full detail: trip reports, ATP profile, diagrams, artifacts.", invoke="customer(name)"),
    _cap("vault.assign_artifact", "vault", "File / transfer an artifact",
         "Move an artifact (e.g. a trip report) into a customer — or to a DIFFERENT customer to fix a "
         "mis-file.", invoke="assign_artifact(artifact_id, customer)"),
    _cap("artifact.search", "artifact", "Search artifacts & trip reports",
         "Full-text search across every artifact and trip-report's content.",
         invoke="search_artifacts(q)"),
    _cap("artifact.get", "artifact", "Read an artifact",
         "Fetch a saved deliverable / conversation in full.", invoke="artifact(id)"),
    _cap("artifact.recent", "artifact", "Recent artifacts",
         "The latest deliverables/conversations.", invoke="artifacts(limit=)"),
]

# --- ATP: the customer technology-profile subsystem ----------------------------------------------
_ATP = [
    _cap("atp.generate", "atp", "Generate ATP profile",
         "Read all of a customer's trip reports (chunked, Copilot WEB) → technologies + 3-paragraph "
         "overview + key contacts; saved as a timestamped generation.",
         invoke="atp_generate(customer)", engine_mode="web", inputs=["customer"]),
    _cap("atp.profile", "atp", "Read ATP profile",
         "Technologies, overview, contacts, topology — for any saved generation.",
         invoke="atp_profile(customer, generation=)", inputs=["customer"]),
    _cap("atp.topology", "atp", "Technology topology diagram",
         "The glowing 10-column topology; each tech shows trip-report appearances + last-seen.",
         invoke="atp_topology(customer)", inputs=["customer"]),
    _cap("atp.edit", "atp", "Edit ATP (techs/overview/contacts)",
         "Hand-edits win across regeneration (pin-and-merge).",
         invoke="atp_save / atp_save_overview / atp_save_contacts", inputs=["customer"]),
]

# --- settings pointers: ATLAS CANNOT change its own settings — it points the user -----------------
_SETTINGS = [
    _cap("settings.trip_report_recipients", "settings-pointer", "Trip-report email recipients",
         "Who the Email button pre-fills.", can_do=False,
         settings_location="Settings → Trip report email recipients"),
    _cap("settings.email_signature", "settings-pointer", "Email signature",
         "Signature appended under emailed reports.", can_do=False,
         settings_location="Settings → Email signature"),
    _cap("settings.auto_email", "settings-pointer", "Auto-open Outlook draft",
         "Auto-draft when a trip report finishes.", can_do=False,
         settings_location="Settings → Auto-open an Outlook draft (checkbox)"),
    _cap("settings.system_pin", "settings-pointer", "System PIN",
         "6-digit PIN required to delete anything.", can_do=False,
         settings_location="Settings → System PIN"),
]

# --- planned: described but not built — the Brain should recommend adding these -------------------
_PLANNED = [
    _cap("planned.network_diagram", "planned", "Excel intake → draw.io network diagram",
         "Turn a customer's Excel intake form into a draw.io network diagram for the customer folder.",
         can_do=False,
         recommend="Add a `network_diagram` skill wrapping the user's existing Excel→draw.io Python; "
                   "inputs: customer + intake file; output: a .drawio + HTML viewer filed under the "
                   "customer's network_diagrams folder."),
]


def manifest() -> list[dict]:
    """Every capability ATLAS exposes (skills auto-derived from the registry) + cannot-do markers."""
    return _skill_caps() + _ENGINE + _VAULT + _ATP + _SETTINGS + _PLANNED


def human_summary() -> str:
    """A friendly, user-facing markdown answer to 'what can ATLAS do / what are your skills?'."""
    m = manifest()
    skills = [c for c in m if c["kind"] == "skill"]
    settings = [c for c in m if c["kind"] == "settings-pointer"]
    planned = [c for c in m if c["kind"] == "planned"]
    lines = ["# What ATLAS can do", "",
             "**🧠 Ask me anything in the command box** — I figure out the right tool, run it, or tell "
             "you what I can't do. For *“is &lt;product&gt; a good fit for &lt;customer&gt;?”* I run a "
             "**brainwave**: research the product and analyze that customer's real environment in "
             "parallel, then give a grounded verdict.", "",
             "## 🛠 Built-in skills"]
    for c in skills:
        inp = f"  _(needs: {', '.join(c['inputs'])})_" if c["inputs"] else ""
        lines.append(f"- **{c['title']}** — {c['description']}{inp}")
    lines += ["", "## 🗂 Customers, profiles & artifacts",
              "- Build & version a customer's **technology profile** from trip reports (topology, "
              "overview, key contacts).",
              "- Every deliverable & trip report is a **searchable artifact** you can read, file to a "
              "customer, or transfer.", ""]
    if settings:
        lines.append("## ⚙ Settings I can point you to (I can't change these myself)")
        lines += [f"- {c['title']} → _{c['settings_location']}_" for c in settings]
        lines.append("")
    if planned:
        lines.append("## 🔭 Not yet — ask and I'll recommend adding the skill")
        lines += [f"- {c['title']} — {c['description']}" for c in planned]
    return "\n".join(lines)


def describe() -> str:
    """A compact text block the Brain's planner can drop into a prompt ('here is everything you can
    do'). Groups by kind; flags cannot-do items with how to handle them."""
    groups: dict[str, list[dict]] = {}
    for c in manifest():
        groups.setdefault(c["kind"], []).append(c)
    label = {"skill": "BUILT-IN SKILLS (run via run_skill)", "engine": "ENGINE PRIMITIVES",
             "vault": "VAULT / CUSTOMERS", "artifact": "ARTIFACTS (memory/retrieval)",
             "atp": "ATP TECHNOLOGY PROFILE", "settings-pointer": "SETTINGS (point the user — ATLAS "
             "cannot change these itself)", "planned": "NOT YET POSSIBLE (recommend adding a skill)"}
    lines = []
    for kind in ("skill", "engine", "vault", "artifact", "atp", "settings-pointer", "planned"):
        items = groups.get(kind) or []
        if not items:
            continue
        lines.append(f"\n## {label.get(kind, kind)}")
        for c in items:
            tail = ""
            if c["kind"] == "settings-pointer":
                tail = f"  → tell the user: {c['settings_location']}"
            elif c["kind"] == "planned":
                tail = f"  → recommend: {c['recommend']}"
            elif c["invoke"]:
                tail = f"  [{c['invoke']}]"
            mode = f" ({c['engine_mode']})" if c["engine_mode"] else ""
            lines.append(f"- {c['title']}{mode}: {c['description']}{tail}")
    return "\n".join(lines).strip()
