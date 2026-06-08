"""Concurrent, persistent job manager — the heart of ATLAS's "everything keeps running" model.

Every request (a skill run, a day gather, a routed command) becomes a Job. One worker thread
is bound to each Copilot Chrome instance in the pool, so up to POOL_SIZE jobs run in parallel.
A job runs to completion on a background thread regardless of where the user navigates, and its
output is always saved (to the vault + the Artifacts log). Jobs are mirrored to vault/jobs.json
so the top status bar survives restarts.
"""
from __future__ import annotations

import dataclasses
import json
import queue
import re
import threading
import time

import config
from atlas.engine import get_pool
from atlas.skills import get_skill
from atlas.store import artifacts

_JOBS_PATH = config.VAULT_DIR / "jobs.json"
_ACTIVE = ("queued", "waiting", "running")


@dataclasses.dataclass
class Job:
    id: str
    kind: str               # a skill key, or "gather_day"
    title: str
    icon: str = "•"
    ctx: dict = dataclasses.field(default_factory=dict)
    status: str = "queued"  # queued | waiting | running | done | error | interrupted
    after: list = dataclasses.field(default_factory=list)
    mode: str = "work"      # Copilot Work (tenant) or Web (public) — set per job
    session_idx: int | None = None
    created: float = dataclasses.field(default_factory=time.time)
    started: float | None = None
    finished: float | None = None
    log: str = ""
    result: dict | None = None
    error: str = ""
    cancel: bool = False    # set by JobManager.cancel() — the user ✕'d this job

    def append(self, msg: str) -> None:
        self.log += str(msg) + "\n"

    # --- views ---
    def summary(self) -> dict:
        """Lightweight record for the status bar / jobs.json (no heavy text)."""
        return {
            "id": self.id, "kind": self.kind, "title": self.title, "icon": self.icon,
            "status": self.status, "session": self.session_idx,
            "created": self.created, "started": self.started, "finished": self.finished,
            "error": self.error, "has_result": bool(self.result),
        }

    def detail(self) -> dict:
        d = self.summary()
        d["log"] = self.log
        d["result"] = self.result
        return d


class JobManager:
    def __init__(self) -> None:
        self.pool = get_pool()
        self._jobs: dict[str, Job] = {}
        self._order: list[str] = []           # submission order
        self._q: queue.Queue[str] = queue.Queue()
        self._mu = threading.Lock()
        self._seq = 0
        self._load_history()
        for s in self.pool.sessions:           # one worker per Chrome instance
            threading.Thread(target=self._worker, args=(s,), daemon=True).start()

    # ---- submission ----
    def submit(self, kind: str, ctx: dict | None = None, title: str = "",
               after: list | None = None, icon: str = "", mode: str = "work") -> str:
        with self._mu:
            self._seq += 1
            jid = f"{int(time.time())}-{self._seq}"
            sk = get_skill(kind)
            job = Job(id=jid, kind=kind, ctx=ctx or {},
                      title=title or (sk.name if sk else kind),
                      icon=icon or (sk.icon if sk else ("🗓" if kind == "gather_day" else "•")),
                      after=list(after or []), mode=mode)
            self._jobs[jid] = job
            self._order.append(jid)
            ready = all(self._is_settled(a) for a in job.after)
            job.status = "queued" if ready else "waiting"
        self._persist()
        if ready:
            self._q.put(jid)
        return jid

    # ---- queries ----
    def list_jobs(self, limit: int = 40) -> list[dict]:
        with self._mu:
            ids = self._order[-limit:][::-1]   # newest first
            return [self._jobs[i].summary() for i in ids if i in self._jobs]

    def get(self, jid: str) -> dict | None:
        j = self._jobs.get(jid)
        return j.detail() if j else None

    def active_count(self) -> int:
        with self._mu:
            return sum(1 for j in self._jobs.values() if j.status in _ACTIVE)

    def cancel(self, jid: str) -> dict:
        """Stop a job the user ✕'d in the Working-on bar. Queued/waiting → drop it before it runs;
        running → force-close the Chrome it's driving so the worker unwinds promptly (interrupted)."""
        with self._mu:
            j = self._jobs.get(jid)
            if not j or j.status not in _ACTIVE:
                return {"ok": False, "state": (j.status if j else "missing")}
            j.cancel = True
            state, sidx = j.status, j.session_idx
            if state in ("queued", "waiting"):
                j.status = "interrupted"
                j.finished = time.time()
        if state in ("queued", "waiting"):
            self._persist()
            self._release_waiters(jid)
            return {"ok": True, "state": "queued-cancelled"}
        # running → force-stop the Chrome session it's on (worker flips it to interrupted when it unwinds)
        sess = next((s for s in self.pool.sessions if s.idx == sidx), None)
        if sess:
            try:
                sess.request_stop()
            except Exception:  # noqa: BLE001
                pass
        return {"ok": True, "state": "running-cancelled"}

    # ---- worker ----
    def _worker(self, session) -> None:
        while True:
            try:
                jid = self._q.get(timeout=10)        # 10s buffer to reuse a warm instance
            except queue.Empty:
                if session.is_open():
                    print(f"[s{session.idx}] idle - closing instance", flush=True)
                    session.close()                  # free this Chrome; reopens on next job
                jid = self._q.get()                  # then block for the next job
            job = self._jobs.get(jid)
            if not job:
                continue
            if job.cancel or job.status == "interrupted":   # ✕'d before it started — skip it
                continue
            job.status = "running"
            job.session_idx = session.idx
            job.started = time.time()
            self._persist()
            try:
                job.result = self._run(session, job)
                job.status = "interrupted" if job.cancel else "done"
            except Exception as e:  # noqa: BLE001
                if job.cancel:
                    job.status = "interrupted"
                    job.append("⏹ Cancelled by user.")
                else:
                    job.error = str(e)
                    job.status = "error"
                    job.append(f"ERROR: {e}")
            job.finished = time.time()
            self._persist()
            self._release_waiters(jid)

    def _run(self, session, job: Job) -> dict:
        """Dispatch a job to its handler and return a result dict."""
        ask = lambda p: session.ask(p, on_log=job.append, mode=job.mode)            # noqa: E731
        ask_chain = lambda ps: session.ask_chain(ps, on_log=job.append, mode=job.mode)  # noqa: E731

        if job.kind == "gather_day":
            from atlas.skills.daily_briefing import gather_day
            date = job.ctx.get("date")
            cards = gather_day(ask_chain, date, job.append)
            return {"text": f"{len(cards)} meeting(s) for {date}", "cards": cards,
                    "files": [], "diagram": None, "data": None}

        if job.kind == "atp_generate":
            from atlas.atp import extract
            ask_all = lambda prompts: session.ask_chain_all(  # noqa: E731
                prompts, on_log=job.append, mode=job.mode, accept=extract.looks_complete)
            res = extract.generate(ask_all, job.ctx.get("customer", ""), job.append)
            return {"text": res.get("text") or res.get("error", "done"),
                    "files": [], "diagram": None, "data": None}

        if job.kind == "brain_route":
            return self._brain_route(session, job)

        if job.kind == "brainwave":
            return self._brainwave(session, job)

        if job.kind == "trip_reports_day":
            return self._trip_reports_day(session, job)

        if job.kind == "skill_over_range":
            return self._skill_over_range(session, job)

        if job.kind == "gather_window":
            return self._gather_window(session, job)

        if job.kind == "finalize_receipt":
            return self._finalize_receipt(session, job)

        if job.kind == "suggest":
            return self._suggest(session, job)

        if job.kind == "bw_research":
            from atlas.brain import brainwave as bw
            txt = session.ask(bw.research_prompt(job.ctx.get("product", ""), job.ctx.get("question", "")),
                              on_log=job.append, mode="web", accept=bw.substantial)
            return {"text": txt, "files": [], "diagram": None, "data": None}

        if job.kind == "bw_cust_saved":         # analyze the customer's OWN saved data (Web, fast)
            from atlas.brain import brainwave as bw
            cust, prod = job.ctx.get("customer", ""), job.ctx.get("product", "")
            q, saved = job.ctx.get("question", ""), job.ctx.get("saved", "")
            if len(saved) <= 22000:              # fits one turn
                txt = session.ask(bw.saved_customer_prompt(cust, prod, q, saved),
                                  on_log=job.append, mode="web", accept=bw.substantial)
            else:                                # chunk ALL reports across one conversation, then ask
                answers = session.ask_chain_all(bw.saved_feed_prompts(cust, prod, q, saved),
                                                on_log=job.append, mode="web", accept=bw.feed_or_substantial)
                txt = next((a for a in reversed(answers) if a and len(a.strip()) > 400), "")
            return {"text": txt, "files": [], "diagram": None, "data": None}

        if job.kind == "bw_cust_live":           # live-tenant freshness/redundancy check (Work)
            from atlas.brain import brainwave as bw
            txt = session.ask(bw.redundancy_prompt(job.ctx.get("customer", ""), job.ctx.get("product", ""),
                                                   job.ctx.get("question", "")),
                              on_log=job.append, mode="work", accept=bw.brief)   # may be short ("nothing new")
            return {"text": txt, "files": [], "diagram": None, "data": None}

        if job.kind == "chat_continue":
            url = job.ctx.get("url") or ""
            prompt = job.ctx.get("prompt") or ""
            aid = job.ctx.get("artifact_id")
            answer = session.ask_at(url, prompt, job.append)
            new_url = session.current_url(wait_conversation=True) or url
            art = artifacts.get(aid) if aid else None
            if art is not None:
                newtext = (art.get("text", "")
                           + f"\n\n**You:** {prompt}\n\n**Copilot:** {answer}").strip()
                artifacts.update(aid, text=newtext, chat_url=new_url)
            return {"text": answer, "files": [], "diagram": None, "data": None, "url": new_url}

        sk = get_skill(job.kind)
        if not sk:
            raise ValueError(f"unknown job kind: {job.kind}")
        res = sk.run(job.ctx, ask, job.append)
        # M365 rewrites the URL to /chat/conversation/<id> a few seconds after the answer.
        url = session.current_url(wait_conversation=True)  # for "continue this chat"
        diagram = res.diagram_html.as_uri() if getattr(res, "diagram_html", None) else None
        data = res.data if isinstance(getattr(res, "data", None), dict) else None
        result = {
            "text": res.text,
            "files": [{"name": p.name, "uri": p.as_uri()} for p in (res.files or [])],
            "diagram": diagram, "data": data, "url": url,
        }
        # Persist substantial skill outputs to the Artifacts browser.
        if res.text and len(res.text) > 20:
            title = (job.ctx.get("account") or job.ctx.get("meeting")
                     or job.ctx.get("question") or job.title)
            # An "ask" becomes a resumable chat: store the transcript, not just the answer.
            art_text = res.text
            if job.kind == "ask" and job.ctx.get("question"):
                art_text = f"**You:** {job.ctx['question']}\n\n**Copilot:** {res.text}"
                result["text"] = art_text
            artifacts.add(sk.key, sk.name, sk.icon, str(title)[:80], art_text,
                          res.files or [], diagram, data, url=url)
        return result

    @staticmethod
    def _child_ids(result: dict) -> list[str]:
        kids = ([result.get("child")] if result.get("child") else []) + (result.get("children") or [])
        return [k for k in kids if k]

    @staticmethod
    def _decision_line(decision: dict | None) -> str:
        """One-line 'Brain logic': what was decided and why, and that classification ran on Copilot Web."""
        d = decision or {}
        action = d.get("action") or "answer"
        skill = d.get("skill") or ""
        why = (d.get("explanation") or "").strip()
        bits = [f"decided **{action}**" + (f" → `{skill}`" if skill else "")]
        if d.get("collection"):
            bits.append(f"collection=`{d['collection']}`")
        if d.get("items"):
            bits.append(f"{len(d['items'])} target(s)")
        head = " · ".join(bits)
        tail = (f" — {why}" if why else "")
        grounding = d.get("grounding") or "classified on Copilot **Web**, grounded on the capability manifest"
        return f"{head}{tail}  \n_({grounding})_"

    def _receipt_body(self, command: str, decision: dict | None, result: dict, *, pending: bool) -> str:
        """The always-present head of a receipt: what you asked, the brain's logic, and the friendly
        result text. The finalizer later appends the agent/Chrome trace + rationale + technology."""
        rcpt = result.get("text", "")
        kids = self._child_ids(result)
        tech = ("Copilot via the Selenium browser pool" if kids
                else "answered directly — in-memory capability manifest, **no Copilot agents (0 Chrome instances)**")
        parts = ["🧠 **Reasoning receipt**", f"**You asked:** {command}" if command else "",
                 f"**Brain logic:** {self._decision_line(decision)}",
                 f"**Technology:** {tech}", "", rcpt]
        if pending and kids:
            parts.append("\n_⏳ Agent trace, Chrome instances, and rationale fill in when the work completes._")
        return "\n\n".join(p for p in parts if p)

    def _log_brainwave(self, command: str, result: dict, decision: dict | None = None) -> dict:
        """Record a brain-console interaction in Brainwave History. EVERY receipt always carries the
        brain's logic + technology up front; if the interaction spawned jobs, a finalize_receipt job
        (gated on those jobs via after=) enriches it with the agent/Chrome/mode trace + a rationale once
        they finish. The deliverable itself still lands in Artifacts separately."""
        try:
            kids = self._child_ids(result)
            body = self._receipt_body(command, decision, result, pending=bool(kids))
            rec = artifacts.add("brainwave", "Brain", "🧠", (command or "Brain")[:80], body, [], None, None)
            if kids:
                self.submit("finalize_receipt",
                            {"receipt_id": rec["id"], "command": command, "child_ids": kids,
                             "decision": decision or {}}, title="🧾 receipt", icon="🧠",
                            mode="web", after=list(kids))
        except Exception:  # noqa: BLE001
            pass
        return result

    def _trace_rows(self, job_ids: list[str]) -> str:
        """A markdown trace table over a set of jobs: agent/job · Copilot mode · Chrome instance · output."""
        rows = ["| Agent / job | Copilot mode | Chrome | Output |", "|---|---|---|---|"]
        for jid in job_ids:
            j = self._jobs.get(jid)
            if not j:
                continue
            inst = f"#{j.session_idx}" if j.session_idx is not None else "—"
            out = (j.result or {}).get("text", "") if j.result else ""
            outdesc = f"{len(out):,} chars" if out else (j.status or "—")
            mode = j.mode or "—"
            rows.append(f"| {j.icon} {j.kind} | {mode} | {inst} | {outdesc} {'✓' if j.status=='done' else ''} |")
        return "\n".join(rows)

    def _finalize_receipt(self, session, job: Job) -> dict:
        """Enrich a receipt once its spawned jobs have settled: append the real agent/Chrome/mode trace,
        a rationale (logic of the answer) for a single deliverable, and the technology footprint. Runs
        AFTER the child jobs (via after=) so it never blocks a pool worker waiting."""
        rid = job.ctx.get("receipt_id")
        command = job.ctx.get("command", "")
        child_ids = list(job.ctx.get("child_ids") or [])
        decision = job.ctx.get("decision") or {}
        art = artifacts.get(rid) if rid else None
        if not art:
            return {"text": "receipt gone", "files": [], "diagram": None, "data": None}

        # Rationale (logic of the answer) — only for a single primary deliverable.
        rationale = ""
        if len(child_ids) == 1:
            cj = self._jobs.get(child_ids[0])
            deliverable = (cj.result or {}).get("text", "") if (cj and cj.result) else ""
            if deliverable.strip():
                from atlas.brain import brainwave as bw
                prompt = (f"The user asked: \"{command}\". ATLAS produced the result below. In 3-6 "
                          f"sentences, explain the LOGIC / RATIONALE of this answer — why it is the "
                          f"right answer, and (if it names people/resources/options) why the top pick "
                          f"fits. Be specific; do not restate the whole result.\n\n=== RESULT ===\n"
                          f"{deliverable[:6000]}")
                rationale = (session.ask(prompt, on_log=job.append, mode="web", accept=bw.brief) or "").strip()

        # Technology footprint from the actual jobs.
        insts, modes = set(), set()
        for jid in child_ids:
            j = self._jobs.get(jid)
            if j:
                if j.session_idx is not None:
                    insts.add(j.session_idx)
                if j.mode:
                    modes.add(j.mode)
        tech = (f"M365 Copilot via the Selenium browser pool · {len(child_ids)} job(s) · "
                f"mode(s): {', '.join(sorted(modes)) or '—'} · Chrome instance(s): "
                f"{', '.join('#'+str(i) for i in sorted(insts)) or '—'}")

        body = (f"🧠 **Reasoning receipt**\n\n**You asked:** {command}\n\n"
                f"**Brain logic:** {self._decision_line(decision)}\n\n"
                f"**How it was worked out** (agents · Copilot mode · Chrome instance · output):\n\n"
                f"{self._trace_rows(child_ids)}\n\n")
        if rationale:
            body += f"**Rationale / logic of the answer:**\n\n{rationale}\n\n"
        elif len(child_ids) > 1:
            body += (f"**Rationale:** decomposed into **{len(child_ids)} parallel run(s)** — each "
                     f"deliverable is its own artifact.\n\n")
        body += f"**Technology used:** {tech}"
        artifacts.update(rid, text=body)
        job.append(f"Receipt {rid} finalized ({len(child_ids)} agent job(s)).")
        return {"text": "receipt finalized", "files": [], "diagram": None, "data": None}

    def _brain_route(self, session, job: Job) -> dict:
        """The Brain: classify a free-text request, act on it, and record the interaction in
        Brainwave History. Each command is a 'brainwave'; its deliverable goes to Artifacts."""
        from atlas.brain import router as brain_router
        text = job.ctx.get("text", "")

        # Fast-path: a question about ATLAS itself is answered from the manifest (no Copilot call).
        if brain_router.is_meta(text):
            job.append("🧠 Meta question — answering from my own capability manifest.")
            return self._log_brainwave(text, self._answer_capabilities(text),
                                       {"action": "capabilities", "grounding": "answered from the "
                                        "in-memory capability manifest — no Copilot round-trip",
                                        "explanation": "A question about ATLAS itself."})

        # Fast-path: "trip reports for all/each of <day>'s meetings" → one trip_report per meeting.
        _day = brain_router.meeting_trip_reports_day(text)
        if _day:
            job.append(f"🧠 Recognized: a trip report for each of {_day}'s meetings.")
            child = self.submit("trip_reports_day", {"day": _day},
                                title=f"🧾 Trip reports — {_day}'s meetings", icon="🧾", mode="work")
            return self._log_brainwave(text, {
                "text": f"🧠 Creating a trip report for each of **{_day}'s** meetings — see job `{child}`.",
                "child": child, "files": [], "diagram": None, "data": None},
                {"action": "plan", "skill": "trip_report",
                 "grounding": "deterministic fast-path (regex) — no Copilot classify needed",
                 "explanation": f"a trip report for each of {_day}'s meetings"})

        ask_web = lambda p: session.ask(p, on_log=job.append, mode="web", accept=brain_router.json_ok)
        try:
            d = brain_router.classify(ask_web, text, job.append)
        except Exception as e:  # noqa: BLE001 — fall back to the deterministic keyword router
            job.append(f"🧠 classify failed ({e}); falling back to keyword routing.")
            d = {}
        action = d.get("action")

        if action == "capabilities":
            return self._log_brainwave(text, self._answer_capabilities(text), d)

        if action == "settings":
            loc = d.get("settings_location") or "the Settings page"
            return self._log_brainwave(text, {
                "text": f"🧠 I can't change settings for you — ATLAS settings are yours to set.\n\n"
                        f"{d.get('explanation','')}\n\n➡ Go to **{loc}**.",
                "files": [], "diagram": None, "data": None}, d)

        if action == "cannot_do":
            return self._log_brainwave(text, {
                "text": f"🧠 I can't do that yet.\n\n{d.get('explanation','')}\n\n"
                        f"💡 **Recommendation:** {d.get('recommendation','')}",
                "files": [], "diagram": None, "data": None}, d)

        if action == "brainwave" and (d.get("ctx") or {}).get("product") and (d.get("ctx") or {}).get("customer"):
            ctx = d["ctx"]
            # Create the Brainwave History entry NOW (so it shows immediately + survives interruption);
            # the brainwave job fills in the full analysis when it finishes.
            ph = artifacts.add("brainwave", "Brainwave", "🧠",
                               f"{ctx.get('product')} for {ctx.get('customer')}"[:80],
                               f"**You asked:** {text}\n\n🧠 Brainwave running — researching "
                               f"**{ctx.get('product')}** and analyzing **{ctx.get('customer')}**'s "
                               f"environment, then synthesizing…", [], None, None)
            child = self.submit("brainwave", {"product": ctx.get("product"), "customer": ctx.get("customer"),
                                              "question": text, "art_id": ph["id"]},
                                title=d.get("title") or f"🧠 {ctx.get('product')} for {ctx.get('customer')}",
                                icon="🧠", mode="web")
            return {"text": f"🧠 {d.get('explanation','')}\n\nStarting a **brainwave** — see job "
                            f"`{child}` in Working on; it'll appear in Brainwave History.",
                    "child": child, "files": [], "diagram": None, "data": None}

        if action == "plan" and d.get("skill"):
            return self._run_plan(text, d)

        if action == "run_skill" and d.get("skill"):
            child = self.submit(d["skill"], d.get("ctx") or {},
                                title=d.get("title") or d["skill"], mode="work")
            return self._log_brainwave(text, {
                "text": f"🧠 {d.get('explanation','')}\n\nRunning **{d['skill']}** — the deliverable will "
                        f"appear in Artifacts (job `{child}`).",
                "child": child, "files": [], "diagram": None, "data": None}, d)

        # Fallback: deterministic keyword router (LLM gave nothing usable).
        from atlas.orchestrator import router as kw
        specs = kw.route(text)
        ids = []
        for spec in specs:
            ids.append(self.submit(spec["kind"], spec.get("ctx", {}), title=spec.get("title", "")))
        routed = ", ".join(s.get("title", s["kind"]) for s in specs) or "nothing"
        return self._log_brainwave(text, {"text": f"🧠 Routed by keyword → {routed}.", "children": ids,
                                          "files": [], "diagram": None, "data": None},
                                   {"action": "keyword fallback", "explanation": f"routed → {routed}",
                                    "grounding": "LLM classify unavailable — deterministic keyword router"})

    def _answer_capabilities(self, text: str) -> dict:
        """Answer a 'what can ATLAS do / what are your skills' question from the manifest."""
        from atlas.brain import capabilities
        return {"text": capabilities.human_summary(), "files": [], "diagram": None, "data": None}

    def _suggest(self, session, job: Job) -> dict:
        """Tier-2 of Continual Suggestions: a single Copilot-Web pass over the focused customer's saved
        data → up to 3 strategic 'next action' chips, cached for the home panel. Fire-and-forget."""
        from atlas.brain import suggest as sg
        customer = (job.ctx.get("customer") or "").strip()
        meeting = job.ctx.get("meeting")
        ctx_key = job.ctx.get("context", "")
        saved = ""
        if customer:
            try:
                from atlas.brain.brainwave import customer_saved_text, resolve_customer
                canon = resolve_customer(customer)
                if canon:
                    saved, _, _ = customer_saved_text(canon, cap=60000)
            except Exception:  # noqa: BLE001
                pass
        accept = lambda t: "::" in (t or "") or len((t or "").strip()) > 60  # noqa: E731
        ans = session.ask(sg.ai_prompt(customer, meeting, saved), on_log=job.append,
                          mode="web", accept=accept)
        items = sg.parse_ai(ans, customer)
        sg.save_cache(ctx_key, items)
        job.append(f"Continual Suggestions refreshed: {len(items)} strategic item(s) for {customer or '—'}.")

        # A readable list — used for BOTH the Brainwave-History record and this job's own result.
        body = f"💡 No suggestions were generated this time for {customer or 'your current context'}."
        if items:
            manual = bool(job.ctx.get("manual"))
            mctx = (f" before \"{meeting['title']}\"" if isinstance(meeting, dict) and meeting.get("title")
                    else "")
            lines = "\n".join(f"- **{it['label']}**  ·  _runs:_ `{it['command']}`" for it in items)
            body = (f"💡 **Suggested next steps** ({'you requested this' if manual else 'automatic'})\n\n"
                    f"Based on **{customer or 'your current context'}**{mctx}:\n\n{lines}\n\n"
                    f"_Open the Home screen and tap a suggestion to run it._")
            try:
                artifacts.add("brainwave", "Suggestions", "💡",
                              f"Suggestions — {customer or 'general'}"[:80], body, [], None, None)
            except Exception:  # noqa: BLE001
                pass
        return {"text": body, "files": [], "diagram": None, "data": None}

    _PLAN_CAP = 15   # safety: don't fan out more than this many parallel jobs from one plan

    @staticmethod
    def _item_ctx(skill_key: str, item: str) -> dict:
        """Put `item` into the skill's primary input (account / meeting / question)."""
        sk = get_skill(skill_key)
        keys = [f.key for f in sk.inputs] if sk else []
        for k in ("account", "customer", "meeting", "question"):
            if k in keys:
                return {k: item}
        return {"account": item} if not keys else {keys[0]: item}

    def _run_plan(self, text: str, d: dict) -> dict:
        """Decompose a multi-target goal into N parallel skill jobs — the planner layer. Each item
        runs the one skill independently (the pool runs POOL_SIZE at a time); each produces an artifact."""
        skill = d.get("skill")
        coll = (d.get("collection") or "").strip()
        # A day-of-meetings collection. Trip reports (the common/cron case) use the reliable
        # trip_reports_day path; any OTHER skill routes through the general skill_over_range coordinator
        # as a single-day range, so "strategic briefings for yesterday's external calls" also works.
        if coll in ("yesterday_meetings", "today_meetings", "tomorrow_meetings"):
            day = coll.split("_", 1)[0]
            if (skill or "trip_report") == "trip_report":
                child = self.submit("trip_reports_day", {"day": day},
                                    title=f"🧾 Trip reports — {day}'s meetings", icon="🧾", mode="work")
                return self._log_brainwave(text, {
                    "text": f"🧠 {d.get('explanation','')}\n\nPlan: a **trip report** for each "
                            f"of **{day}'s** meetings — see job `{child}`.",
                    "child": child, "files": [], "diagram": None, "data": None}, d)
            import datetime as _dt
            date = (_dt.date.today() + _dt.timedelta(days={"yesterday": -1, "tomorrow": 1}.get(day, 0))).isoformat()
            sk = get_skill(skill)
            child = self.submit("skill_over_range",
                                {"start": date, "end": date, "filter": (d.get("filter") or "").strip(),
                                 "skill": skill},
                                title=f"{sk.icon if sk else '🧠'} {sk.name if sk else skill} — {day}"[:80],
                                icon=(sk.icon if sk else "🧠"), mode="work")
            return self._log_brainwave(text, {
                "text": f"🧠 {d.get('explanation','')}\n\nPlan: **{(sk.name if sk else skill).lower()}** for "
                        f"**{day}'s** meetings — see job `{child}`.",
                "child": child, "files": [], "diagram": None, "data": None}, d)

        # Meetings across a SPAN of dates → the windowed gather → filter → throttled fan-out coordinator.
        if coll == "date_range":
            from atlas.brain import timespan
            rng = d.get("range") if isinstance(d.get("range"), dict) else {}
            cr = timespan.clamp_range(rng.get("start", ""), rng.get("end", ""))
            if not cr:
                return self._log_brainwave(text, {
                    "text": "🧠 I understood this as meetings over a date range but couldn't read the "
                            "dates — try naming them like 'May 21 to June 5, 2026'.",
                    "files": [], "diagram": None, "data": None}, d)
            start, end = cr[0].isoformat(), cr[1].isoformat()
            sk = get_skill(skill) if skill else None
            sk_label = (sk.name if sk else (skill or "trip report")).lower()
            child = self.submit("skill_over_range",
                                {"start": start, "end": end, "filter": (d.get("filter") or "").strip(),
                                 "skill": skill or "trip_report"},
                                title=f"🧾 {sk.name if sk else 'Trip reports'} — {start} → {end}"[:80],
                                icon=(sk.icon if sk else "🧾"), mode="work")
            return self._log_brainwave(text, {
                "text": f"🧠 {d.get('explanation','')}\n\nPlan: **{sk_label}** for my "
                        f"meetings **{start} → {end}**"
                        + (" (external customers only)" if (d.get('filter') == 'external_customer') else "")
                        + f" — gathering the calendar in parallel, then working through them a few at a "
                          f"time. See job `{child}`.",
                "child": child, "files": [], "diagram": None, "data": None}, d)

        items = [str(i).strip() for i in (d.get("items") or []) if str(i).strip()]
        if coll == "customers":
            from atlas.store import customers
            items = [c["name"] for c in customers.list_customers()]
        items = list(dict.fromkeys(items))                 # de-dupe, keep order
        if not skill or not items:
            return self._log_brainwave(text, {
                "text": "🧠 I understood this as a multi-step plan but couldn't resolve the targets — "
                        "try naming them explicitly.", "files": [], "diagram": None, "data": None}, d)
        capped = items[:self._PLAN_CAP]
        ids = [self.submit(skill, self._item_ctx(skill, it), title=f"{skill} — {it}"[:80],
                           icon="🧠", mode="work") for it in capped]
        listing = "\n".join(f"- {it}" for it in capped)
        more = (f"\n\n_(ran the first {self._PLAN_CAP} of {len(items)}; ask again for the rest)_"
                if len(items) > self._PLAN_CAP else "")
        return self._log_brainwave(text, {
            "text": f"🧠 {d.get('explanation','')}\n\n**Plan:** running **{skill}** for "
                    f"**{len(capped)} target(s)** in parallel — each lands in Artifacts:\n\n{listing}{more}",
            "children": ids, "files": [], "diagram": None, "data": None}, d)

    def _trip_reports_day(self, session, job: Job) -> dict:
        """Create a trip report for each meeting of a given day (yesterday / today / tomorrow). For
        today only PAST meetings qualify; for yesterday all do; tomorrow has no transcripts yet.
        Submits one trip_report job per meeting, each stamped with THAT day's date."""
        import datetime
        from atlas.artifacts import dashboard_html
        from atlas.skills.daily_briefing import gather_day, load_for
        day = job.ctx.get("day", "today")
        offset = {"yesterday": -1, "tomorrow": 1}.get(day, 0)
        date = (datetime.date.today() + datetime.timedelta(days=offset)).isoformat()
        if day == "tomorrow":
            return {"text": f"Tomorrow's meetings ({date}) haven't happened yet — no transcripts to "
                            f"report on. Try this for yesterday or today.",
                    "files": [], "diagram": None, "data": None}
        cards = load_for(date)
        if not cards:
            job.append(f"{day.capitalize()}'s meetings aren't cached yet — gathering them now…")
            ask_chain = lambda ps: session.ask_chain(ps, on_log=job.append, mode=job.mode)  # noqa: E731
            cards = gather_day(ask_chain, date, job.append) or []
        enriched = dashboard_html.enrich(cards, day_kind=day)
        past = [m for m in enriched if m.get("past") and (m.get("title") or "").strip()]
        if not past:
            return {"text": f"No {day} meetings to report on ({date}).",
                    "files": [], "diagram": None, "data": None}
        items = [{"label": m["title"], "date": date} for m in past]
        ids = self._fan_out("trip_report", items)
        listing = "\n".join(f"- {m['label']}" for m in items)
        job.append(f"Queued {len(ids)} trip report(s) for {day} ({date}).")
        return {"text": f"🧾 Queued **{len(ids)} trip report(s)** for {day}'s meetings ({date}):\n\n{listing}",
                "children": ids, "files": [], "diagram": None, "data": None}

    # ---- date-range trip reports: windowed gather → filter → throttled fan-out ----
    _FANOUT_CAP = 40   # safety: don't queue more than this many trip reports from one range

    # CONSERVATIVE skip-list: only titles that are unambiguously NOT a reportable customer meeting.
    # Ambiguous words like "sync"/"team meeting" are deliberately NOT here — a customer's "Monthly
    # Sync" is real — those are judged by the external-customer reasoning pass instead.
    _SKIP_RE = re.compile(
        r"\b(lunch|admin|focus(?:\s*time)?|hold|blocked?|ooo|out\s*of\s*office|pto|vacation|"
        r"1:1|one[\s-]?on[\s-]?one|internal|stand[\s-]?up|all[\s-]?hands|break|busy|tentative|"
        r"no\s+meetings?)\b",
        re.I)

    def _fan_out(self, skill: str, items: list[dict]) -> list[str]:
        """Submit one `skill` job per item, capped at _FANOUT_CAP, with a SLIDING-WINDOW dependency so
        at most `batch_concurrency` (default 4) run at once — bounds RAM. Each item is a dict
        {"label": <primary input value>, "date": <opt>, "account": <opt>}; ctx is built from the
        skill's OWN declared inputs (so trip_report gets meeting+date, account-skills get account, and
        meeting_prep gets both). Returns the child job ids."""
        from atlas.store import settings
        sk = get_skill(skill)
        keys = [f.key for f in sk.inputs] if sk else []
        icon = sk.icon if sk else "🧾"
        name = sk.name if sk else skill
        win = max(1, int(settings.load().get("batch_concurrency") or 4))
        capped = items[:self._FANOUT_CAP]
        ids: list[str] = []
        for i, it in enumerate(capped):
            label = it.get("label", "")
            ctx: dict = {}
            if "meeting" in keys:
                ctx["meeting"] = label
                if "date" in keys and it.get("date"):
                    ctx["date"] = it["date"]
                if "account" in keys and it.get("account"):
                    ctx["account"] = it["account"]
            elif "account" in keys:
                ctx["account"] = label
            elif "customer" in keys:
                ctx["customer"] = label
            elif "question" in keys:
                ctx["question"] = label
            else:
                ctx["account"] = label   # best effort for an unusual single-input skill
            after = [ids[i - win]] if i >= win else []     # job i waits on job i-win → ≤win concurrent
            ids.append(self.submit(skill, ctx, title=f"{name} — {label[:40]}"[:80],
                                   icon=icon, mode="work", after=after))
        return ids

    def _gather_window(self, session, job: Job) -> dict:
        """Gather every meeting across this window's dates on ONE Copilot Work instance (sequential
        turns, reusing daily_briefing.gather_day), each tagged with its date."""
        from atlas.skills.daily_briefing import gather_day
        dates = [str(x) for x in (job.ctx.get("dates") or [])]
        ask_chain = lambda ps: session.ask_chain(ps, on_log=job.append, mode="work")  # noqa: E731
        meetings: list[dict] = []
        for ds in dates:
            cards = gather_day(ask_chain, ds, job.append) or []
            for c in cards:
                if (c.get("title") or "").strip():
                    meetings.append({"date": ds, "title": c["title"], "body": c.get("body", "")})
        job.append(f"Window {dates[0] if dates else '?'}…{dates[-1] if dates else '?'}: "
                   f"{len(meetings)} meeting(s).")
        return {"text": f"{len(meetings)} meeting(s) across {len(dates)} day(s).",
                "meetings": meetings, "files": [], "diagram": None, "data": None}

    def _filter_external_customer(self, session, job, meetings: list[dict]) -> list[dict]:
        """Copilot Web reasoning pass: keep only EXTERNAL CUSTOMER meetings. Falls back to the input
        (already deterministically de-junked) if the pass returns nothing usable — never drops all."""
        if not meetings:
            return meetings
        listing = "\n".join(f"{i + 1}. {m['title']}" for i, m in enumerate(meetings))
        prompt = (
            "Below is a numbered list of my calendar meeting titles. Identify which ones are "
            "EXTERNAL meetings with a CUSTOMER / prospect / partner (not my own company). EXCLUDE "
            "internal syncs, team meetings, 1:1s, standups, all-hands, lunch, admin/focus/hold blocks, "
            "OOO/PTO. Reply with ONLY the numbers of the external customer meetings, comma-separated "
            "(e.g. 1, 4, 5). If none qualify, reply exactly: NONE.\n\n" + listing)
        accept = lambda t: bool(re.search(r"\d", t or "")) or "none" in (t or "").lower()  # noqa: E731
        ans = session.ask(prompt, on_log=job.append, mode="web", accept=accept) or ""
        if "none" in ans.lower() and not re.search(r"\d", ans):
            job.append("External-customer filter: Copilot judged none external — keeping deterministic set.")
            return meetings
        nums = {int(n) for n in re.findall(r"\d+", ans)}
        kept = [m for i, m in enumerate(meetings, 1) if i in nums]
        if not kept:
            job.append("External-customer filter returned nothing parseable — keeping deterministic set.")
            return meetings
        job.append(f"External-customer filter: kept {len(kept)} of {len(meetings)} meeting(s).")
        return kept

    def _skill_over_range(self, session, job: Job) -> dict:
        """General coordinator: gather the meetings across a date range (parallel windows, Copilot Work
        → Graph calendar), filter them (skip internal/lunch/admin; optionally external-only via a Web
        reasoning pass), then run ANY skill over them AT THE SKILL'S OWN GRANULARITY — per-meeting for
        meeting skills (trip_report/meeting_prep), or reduced to distinct customers for account skills
        (strategic_briefing/battlecard/…). Fans out a few at a time."""
        import datetime

        from atlas.brain import timespan
        from atlas.store import settings

        cr = timespan.clamp_range(job.ctx.get("start", ""), job.ctx.get("end", ""))
        if not cr:
            return {"text": "Couldn't read the date range.", "files": [], "diagram": None, "data": None}
        start, end = cr
        today = datetime.date.today()
        # Only days that have already happened can have transcripts to report on.
        dates = [d for d in timespan.date_list(start, end) if datetime.date.fromisoformat(d) <= today]
        if not dates:
            return {"text": f"The range {start}…{end} is entirely in the future — no transcripts yet.",
                    "files": [], "diagram": None, "data": None}
        size = int(settings.load().get("gather_window_size") or 5)
        wins = timespan.windows(dates, size)
        job.append(f"🗓 Gathering {len(dates)} day(s) in {len(wins)} parallel window(s) of ≤{size}…")

        gids = [self.submit("gather_window", {"dates": w},
                            title=f"🗓 Gather {w[0]}…{w[-1]}", icon="🗓", mode="work") for w in wins]

        deadline = time.time() + 1200
        while time.time() < deadline:
            if all(self._is_settled(g) for g in gids):
                break
            time.sleep(2)

        meetings: list[dict] = []
        for g in gids:
            j = self._jobs.get(g)
            for m in ((j.result or {}).get("meetings") or []) if (j and j.result) else []:
                meetings.append(m)
        # de-dupe by (date, normalized title)
        seen, uniq = set(), []
        for m in meetings:
            k = (m.get("date"), re.sub(r"[^a-z0-9]+", "", (m.get("title") or "").lower()))
            if k[1] and k not in seen:
                seen.add(k)
                uniq.append(m)
        job.append(f"Collected {len(uniq)} distinct meeting(s) across the range.")

        # Deterministic skip-list (junk / internal / admin), then optional external-customer reasoning.
        kept = [m for m in uniq if not self._SKIP_RE.search(m.get("title") or "")]
        if (job.ctx.get("filter") or "") == "external_customer":
            kept = self._filter_external_customer(session, job, kept)
        if not kept:
            return {"text": f"No matching meetings found in {start}…{end} to work on.",
                    "files": [], "diagram": None, "data": None}

        # Reduce the meetings to the chosen skill's GRANULARITY.
        skill = job.ctx.get("skill") or "trip_report"
        sk = get_skill(skill)
        keys = [f.key for f in sk.inputs] if sk else ["meeting"]
        if not keys:
            return {"text": f"**{sk.name if sk else skill}** doesn't take a per-meeting or per-customer "
                            f"target, so it can't be fanned out over a date range. "
                            f"(Found {len(kept)} meeting(s) in {start}…{end}.)",
                    "files": [], "diagram": None, "data": None}
        if "meeting" in keys:
            items = [{"label": m["title"], "date": m["date"],
                      "account": (self._derive_cust(m["title"]) if "account" in keys else "")}
                     for m in kept]
            unit = "meeting"
        else:                                  # account / customer skill → distinct customers
            custs = self._distinct_customers(session, job, kept)
            items = [{"label": c} for c in custs]
            unit = "customer"

        ids = self._fan_out(skill, items)
        more = (f"\n\n_(queued the first {self._FANOUT_CAP}; ask again for the rest)_"
                if len(items) > self._FANOUT_CAP else "")
        listing = "\n".join(
            f"- {it['label']}" + (f" ({it['date']})" if it.get("date") else "") for it in items[:self._FANOUT_CAP])
        win = max(1, int(settings.load().get("batch_concurrency") or 4))
        label = (sk.name if sk else skill)
        result = {
            "text": f"{sk.icon if sk else '🧾'} **{len(ids)} {label}{'s' if len(ids) != 1 else ''}** "
                    f"queued for {start} → {end} (one per {unit}, ≤{win} at a time):\n\n{listing}{more}",
            "children": ids, "files": [], "diagram": None, "data": None}
        return self._log_brainwave(
            f"{label} {start} → {end}"
            + (" (external customers)" if (job.ctx.get('filter') == 'external_customer') else ""),
            result,
            {"action": "plan", "skill": skill,
             "explanation": f"{label} over {start} → {end}, one per {unit}",
             "grounding": "date-range coordinator: parallel calendar gather → filter → granularity"})

    @staticmethod
    def _derive_cust(title: str) -> str:
        try:
            from atlas.skills.trip_report import _derive_customer
            return _derive_customer(title) or ""
        except Exception:
            return ""

    def _distinct_customers(self, session, job, meetings: list[dict]) -> list[str]:
        """Reduce external meetings to the DISTINCT customers/companies they involve (for account-level
        skills). Copilot Web reasoning pass, with a heuristic fallback; each name snapped to a known
        vault customer when possible; case-insensitive de-dupe; capped at _FANOUT_CAP."""
        from atlas.brain.brainwave import resolve_customer
        names: list[str] = []
        if meetings:
            listing = "\n".join(f"- {m['title']}" for m in meetings)
            prompt = (
                "Below are my external customer meeting titles. List the DISTINCT customer / company "
                "names involved — one per line, the company name only (no dates, no extra words). "
                "Merge variants of the same company into one. If you can't tell, skip it.\n\n" + listing)
            accept = lambda t: len((t or "").strip()) > 1  # noqa: E731
            ans = session.ask(prompt, on_log=job.append, mode="web", accept=accept) or ""
            for ln in ans.splitlines():
                s = re.sub(r"^[\s\-*•\d.]+", "", ln).strip()
                if s and len(s) < 80 and not s.lower().startswith(("here", "the ", "these", "distinct")):
                    names.append(s)
        if not names:                           # fallback: derive from titles
            names = [self._derive_cust(m["title"]) for m in meetings]
        # snap to canonical vault customers + de-dupe (case-insensitive)
        out, seen = [], set()
        for n in names:
            n = (resolve_customer(n) or n).strip()
            k = re.sub(r"[^a-z0-9]+", "", n.lower())
            if k and k not in seen:
                seen.add(k)
                out.append(n)
        job.append(f"Reduced to {len(out)} distinct customer(s): {', '.join(out[:10])}"
                   + ("…" if len(out) > 10 else ""))
        return out[:self._FANOUT_CAP]

    def _brainwave(self, session, job: Job) -> dict:
        """Fan out a Web product-research sub-agent ‖ a Work customer-analysis sub-agent, merge their
        outputs into an ephemeral brainwave file, then synthesize a grounded verdict on this thread
        and save it as a `brainwave` artifact."""
        from atlas.brain import brainwave as bw
        product = (job.ctx.get("product") or "").strip()
        cname = (job.ctx.get("customer") or "").strip()
        question = job.ctx.get("question") or job.title
        resolved = bw.resolve_customer(cname) or cname
        is_known = bool(bw.resolve_customer(cname))

        # Rule 1: the customer's OWN saved data (trip reports + ATP) is the #1 source.
        saved_text, n_used, n_total = bw.customer_saved_text(resolved) if is_known else ("", 0, 0)
        job.append(f"🧠 Brainwave: is “{product}” a good fit for {resolved}?")
        job.append(f"   Loaded {resolved}'s saved data: {n_used}/{n_total} trip report(s) "
                   f"+ ATP profile ({len(saved_text):,} chars)." if saved_text
                   else f"   No saved trip reports/profile for {resolved}; relying on the live tenant check.")

        rid = self.submit("bw_research", {"product": product, "question": question},
                          title=f"🔎 Research — {product}", icon="🔎", mode="web")
        sid = self.submit("bw_cust_saved", {"customer": resolved, "product": product,
                                            "question": question, "saved": saved_text},
                          title=f"🗂 {resolved} saved data", icon="🗂", mode="web")
        lid = self.submit("bw_cust_live", {"customer": resolved, "product": product, "question": question},
                          title=f"🏢 {resolved} live check", icon="🏢", mode="work")
        job.append(f"   Fanned out 3 agents in parallel: research {rid} (Web) ‖ saved-data {sid} "
                   f"(Web) ‖ live-tenant {lid} (Work). Waiting…")

        deadline = time.time() + 600
        while time.time() < deadline:
            js = [self._jobs.get(x) for x in (rid, sid, lid)]
            if all(j and j.status in ("done", "error") for j in js):
                break
            time.sleep(2)

        def _txt(jid):
            j = self._jobs.get(jid)
            return (j.result or {}).get("text", "") if (j and j.result) else ""
        research, saved, live = _txt(rid), _txt(sid), _txt(lid)
        job.append(f"   research {len(research):,} ‖ saved {len(saved):,} ‖ live {len(live):,} chars. "
                   f"Synthesizing…")

        wave_dir = config.VAULT_DIR / "brain" / "brainwaves" / job.id
        wave_dir.mkdir(parents=True, exist_ok=True)
        wave = (f"# Brainwave: {question}\n\n## Product research — {product}\n{research}\n\n"
                f"## {resolved} — from saved trip reports/profile (PRIMARY)\n{saved}\n\n"
                f"## {resolved} — live M365 freshness check\n{live}\n")
        (wave_dir / "wave.md").write_text(wave, encoding="utf-8")

        synth = session.ask(bw.synth_prompt(product, resolved, question, research, saved, live),
                            on_log=job.append, mode="web", accept=bw.substantial)
        url = session.current_url(wait_conversation=True)
        synth = (synth or "").strip() or "_Synthesis did not complete — see the detail in wave.md._"

        # Orchestration trace (the user wants the agents/instances + brain logic in the result).
        def _sess(jid):
            j = self._jobs.get(jid)
            return f"#{j.session_idx}" if (j and j.session_idx is not None) else "#?"
        ok = "✓"
        srcnote = (f"{n_used}/{n_total} reports + ATP" if saved_text else "no saved data")
        trace = (
            f"# 🧠 Brainwave — {product} for {resolved}\n\n"
            f"**How the brain worked this out** (Rule 1: the customer's saved data comes first):\n\n"
            f"| Step | Agent | Copilot mode | Chrome | Output |\n"
            f"|---|---|---|---|---|\n"
            f"| 1 | 🗂 {resolved} saved data ({srcnote}) | Web | {_sess(sid)} | "
            f"{len(saved):,} chars {ok if saved else '—'} |\n"
            f"| 1 | 🔎 Product research — {product} | Web | {_sess(rid)} | "
            f"{len(research):,} chars {ok if research else '—'} |\n"
            f"| 1 | 🏢 Live tenant freshness check | Work | {_sess(lid)} | "
            f"{len(live):,} chars {ok if live else '—'} |\n"
            f"| 2 | 🧬 Synthesis | Web | #{job.session_idx if job.session_idx is not None else '?'} | "
            f"verdict ↓ |\n\n"
            f"The three step-1 agents ran **in parallel**. Full detail is saved in `wave.md`.\n\n"
            f"---\n\n{synth}")

        wave_file = {"name": "wave.md", "uri": (wave_dir / "wave.md").as_uri()}
        art_id = job.ctx.get("art_id")
        if art_id and artifacts.get(art_id):     # fill in the entry created when the brainwave started
            artifacts.update(art_id, text=trace, files=[wave_file], chat_url=url,
                             customer=(resolved if is_known else ""))
        else:                                     # brainwave job run directly (no pre-created entry)
            rec = artifacts.add("brainwave", "Brainwave", "🧠", f"{product} for {resolved}"[:80], trace,
                                [wave_dir / "wave.md"], None, None, url=url)
            art_id = rec["id"]
            if is_known:
                artifacts.update(art_id, customer=resolved)
        return {"text": trace, "files": [wave_file],
                "diagram": None, "data": None, "url": url, "artifact_id": art_id}

    # ---- dependency helpers ----
    def _is_done(self, jid: str) -> bool:
        j = self._jobs.get(jid)
        return bool(j and j.status == "done")

    def _is_settled(self, jid: str) -> bool:
        """A dependency is SETTLED once it reaches any terminal state. Used to RELEASE waiters — so a
        dependency that errors/was interrupted still lets its dependents run (a failed trip report must
        not deadlock the rest of a sliding-window fan-out). Unknown ids count as settled (already gone)."""
        j = self._jobs.get(jid)
        return (j is None) or (j.status in ("done", "error", "interrupted"))

    def _release_waiters(self, finished_id: str) -> None:
        ready = []
        with self._mu:
            for j in self._jobs.values():
                if j.status == "waiting" and all(self._is_settled(a) for a in j.after):
                    j.status = "queued"
                    ready.append(j.id)
        for jid in ready:
            self._q.put(jid)

    # ---- persistence ----
    def _persist(self) -> None:
        try:
            with self._mu:
                recs = [self._jobs[i].summary() for i in list(self._order) if i in self._jobs]
            _JOBS_PATH.write_text(json.dumps(recs[-200:], indent=2, ensure_ascii=False),
                                  encoding="utf-8")
        except Exception:
            pass

    def _load_history(self) -> None:
        if not _JOBS_PATH.exists():
            return
        try:
            for rec in json.loads(_JOBS_PATH.read_text(encoding="utf-8")):
                jid = rec.get("id")
                if not jid:
                    continue
                status = rec.get("status")
                if status in _ACTIVE:        # left over from a previous run
                    status = "interrupted"
                self._jobs[jid] = Job(
                    id=jid, kind=rec.get("kind", ""), title=rec.get("title", ""),
                    icon=rec.get("icon", "•"), status=status,
                    session_idx=rec.get("session"), created=rec.get("created", time.time()),
                    started=rec.get("started"), finished=rec.get("finished"),
                    error=rec.get("error", ""))
                self._order.append(jid)
        except Exception:
            pass


_manager: JobManager | None = None
_mlock = threading.Lock()


def get_manager() -> JobManager:
    global _manager
    with _mlock:
        if _manager is None:
            _manager = JobManager()
        return _manager
