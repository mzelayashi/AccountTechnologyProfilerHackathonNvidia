"""The ATLAS inference engine: Microsoft 365 Copilot, driven through the browser.

One persistent, signed-in Chrome session (reused across skills). `ask(prompt)` types
the prompt into Copilot, submits, and returns the finished answer — with completion
detection that skips the "Lining things up…" loading placeholders. No API key/tokens.
"""
from __future__ import annotations

import os
import re
import threading
import time
from typing import Callable

import config

# Temporary kill-switch (set by the Linux launcher run_atlas_linux.py). When on, ATLAS never
# launches a Chrome/Copilot session — every inference call returns a stub instead. This is the
# seam where the local Nemotron engine will plug in (see NEMOTRON_ARCHITECTURE.md).
_ENGINE_DISABLED_MSG = ("⚙️ The Copilot/Chrome engine is disabled on this machine — the Nemotron "
                        "engine will replace it. No browser was opened.")


def _engine_disabled() -> bool:
    return os.getenv("ATLAS_COPILOT_DISABLED") == "1"

# Proven selectors (validated live against m365.cloud.microsoft/chat).
_INPUT_SELECTORS = ['[role="textbox"]', 'div[contenteditable="true"]', "textarea"]
_ANSWER_SELECTORS = [
    '[data-testid*="message"]',
    '[data-content="ai-message"]',
    '[role="article"]',
    'div[class*="message-body"]',
    'div[class*="message"]',
]
_LOADING = (
    "lining things up", "searching", "working on", "gathering", "generating",
    "thinking", "one moment", "getting things", "let me ",
)
# Intermediate "reasoning out loud" traces Copilot streams BEFORE the real answer (e.g.
# "Searching for meeting details… I am looking into…", "Finalizing citations… I'm planning to
# append…"). They can be long (so the <80-char loading filter misses them) and sit stable while
# Copilot keeps working — we must NOT accept them as the finished answer. They take the form of a
# short gerund status header (no punctuation) followed by first-person narration.
_PREAMBLE = (
    "searching for", "i am looking into", "i'm looking into", "looking into",
    "let me look", "let me check", "i'll look", "i will look", "i will extract",
    "i am checking", "i'm checking", "give me a moment", "one moment",
    "let me gather", "i am gathering", "i'm gathering", "working on it",
    "i'm planning", "i am planning", "i'll start", "i will start", "first, i",
)
_GERUNDS = (
    "searching", "finalizing", "reasoning", "planning", "analyzing", "reviewing",
    "gathering", "looking", "checking", "scoring", "compiling", "identifying",
    "processing", "generating", "summarizing", "evaluating", "collecting", "retrieving",
    "preparing", "organizing", "formatting", "citing", "thinking", "considering",
    "examining", "assessing", "calculating", "determining", "extracting", "scanning",
    "fetching", "loading", "working", "mapping", "structuring", "drafting",
)


def _is_preamble(text: str) -> bool:
    tl = (text or "").lower().strip()
    if any(tl.startswith(p) for p in _PREAMBLE):
        return True
    # A short gerund status header with no sentence punctuation = reasoning chatter, not an answer.
    first = tl.split("\n", 1)[0].strip()
    words = first.split()
    if words and words[0] in _GERUNDS and len(words) <= 6 and not first.endswith((":", ".", "?")):
        return True
    return False
# Deterministic completion signal: we ask Copilot to end every reply with this marker,
# then detect it to know the answer is fully finished (no timing guesswork).
SENTINEL = "ATLAS-RESPONSE-COMPLETE"
# Kept gentle on purpose: phrasing like "write nothing after it / exact marker" reads like a
# jailbreak to Copilot's guardrail and can trigger refusals. We only need the marker to appear.
_SENTINEL_HINT = f" When you're finished, please add this line at the very end: {SENTINEL}"
# When Copilot ECHOES our pasted prompt (common in Web mode), the echo carries this instruction
# phrase AND the literal marker — which would fool completion detection into returning the prompt as
# the answer. A real answer only appends the bare marker, never this phrase. Used to exclude echoes.
_ECHO_SIG = "please add this line at the very end"

# Copilot guardrail refusals — treat these as NON-answers so they never bury real data.
_REFUSALS = (
    "can't chat about this", "let's try a different topic", "can't help with that",
    "i'm unable to", "i can't assist", "i can't provide", "i can't continue",
)


def _is_refusal(text: str) -> bool:
    t = (text or "").lower()
    return bool(t) and len(t) < 400 and any(m in t for m in _REFUSALS)
# The real composer Send button: aria-label="Send", class contains "fai-SendButton".
# Use EXACT aria / the SendButton class — substring "Send" wrongly matched "Sendero" chips!
_SEND_SELECTORS = [
    'button[aria-label="Send" i]', 'button[class*="SendButton"]',
    'button[title="Send" i]', 'button[aria-label="Send message" i]',
]

# The top-center Work | Web segmented toggle (discovered live). "work" = M365 tenant grounding
# (calendar/files); "web" = public web Copilot (for the ATP report generation).
_MODE_TOGGLE = {"work": 'button[data-testid="toggle-work"]',
                "web": 'button[data-testid="toggle-web"]'}


def _safe(fn):
    try:
        return fn()
    except Exception:
        return None


class Session:
    """One Copilot browser session bound to its OWN Chrome profile (a pool slot).

    Sessions are independent: each drives its own Chrome process and only ever touches
    its own profile dir, so concurrent sessions never kill or block each other."""

    def __init__(self, profile_dir=None, idx: int = 0) -> None:
        self.profile_dir = profile_dir or config.CHROME_PROFILE_DIR
        self.idx = idx
        self._driver = None
        self._lock = threading.Lock()  # one job at a time on this session
        self._stop = threading.Event()  # set by request_stop() to cancel the in-flight turn

    def request_stop(self) -> None:
        """Cancel whatever this session is doing RIGHT NOW: signal the wait loops to bail, then
        force-close this session's Chrome (scoped to THIS profile only). Called from another thread —
        takes no lock, so it works even while a worker holds the session mid-ask. Self-heals on next job."""
        self._stop.set()
        try:
            self._kill_profile_chrome()
        except Exception:
            pass
        self.close()

    # ---- lifecycle ----
    def _chrome(self):
        if _engine_disabled():            # hard backstop — no browser may ever launch while disabled
            raise RuntimeError("Copilot/Chrome engine is disabled (ATLAS_COPILOT_DISABLED=1)")
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options

        opts = Options()
        opts.add_argument(f"--user-data-dir={self.profile_dir}")
        opts.add_argument("--window-size=1100,860")  # real, fully-rendered viewport (clipboard paste needs it)
        # Default: launch off every monitor so the window never visibly pops up. Debug toggle
        # (Settings → show_chrome_windows) brings it back on-screen at 60,60.
        pos = "60,60" if self._show_windows() else "-32000,-32000"
        opts.add_argument(f"--window-position={pos}")
        opts.add_argument("--no-first-run")
        opts.add_argument("--no-default-browser-check")
        return webdriver.Chrome(options=opts)

    @staticmethod
    def _show_windows() -> bool:
        """Debug toggle: when true the pool's Chrome opens visible; default = hidden/minimized."""
        try:
            from atlas.store import settings
            return bool(settings.load().get("show_chrome_windows"))
        except Exception:
            return False

    def _remove_locks(self) -> None:
        for name in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
            p = self.profile_dir / name
            try:
                if p.exists():
                    p.unlink()
            except Exception:
                pass

    def _kill_profile_chrome(self) -> None:
        """Kill any leftover Chrome using THIS session's profile only (exact dir name, so we
        never disturb the other pool instances). Profile names are unique (chrome_profile_0..N)."""
        import subprocess
        name = self.profile_dir.name  # e.g. chrome_profile_0 — unique per slot
        ps = ("Get-CimInstance Win32_Process -Filter \"Name='chrome.exe'\" | "
              f"Where-Object {{ $_.CommandLine -like '*{name}*' }} | "
              "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }")
        try:
            subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           timeout=10, capture_output=True)
        except Exception:
            pass

    def _fresh(self, on_log: Callable[[str], None]):
        """Open a new window AND a NEW Copilot conversation (no context bleed). Retries once
        if the Chrome session dies (e.g. a transient profile collision)."""
        for attempt in range(2):
            self.close()
            self._kill_profile_chrome()
            self._remove_locks()
            time.sleep(0.8)  # let the profile lock release before relaunch
            on_log(f"Opening Copilot instance #{self.idx}…")
            try:
                self._driver = self._chrome()
                d = self._driver
                if not self._show_windows():
                    # Minimize the instant it exists — BEFORE the ~3s load — so it never flashes
                    # on screen (it's already off-screen via --window-position; this also keeps it
                    # out of the taskbar foreground). Debug mode leaves it visible.
                    _safe(d.minimize_window)
                d.get(config.COPILOT_URL)
                time.sleep(3)
                url = _safe(lambda: d.current_url)
                if not url:  # dead session — retry
                    print(f"[s{self.idx}] launch attempt {attempt + 1}: dead session, retrying", flush=True)
                    continue
                print(f"[s{self.idx}] landed: {url}", flush=True)
                if not self._show_windows():
                    _safe(d.minimize_window)  # belt-and-suspenders: stay out of the way of the ATLAS window
                self._new_chat(d, on_log)
                print(f"[s{self.idx}] after new-chat: {_safe(lambda: d.current_url)}", flush=True)
                return d
            except Exception as e:  # noqa: BLE001
                print(f"[s{self.idx}] launch attempt {attempt + 1} failed: {e}", flush=True)
                time.sleep(1)
        return self._driver

    def _new_chat(self, driver, on_log: Callable[[str], None]) -> bool:
        """Click Copilot's 'New chat' so each query starts a clean conversation."""
        from selenium.webdriver.common.by import By

        sels = [
            'button[aria-label*="New chat" i]', '[aria-label*="New chat" i]',
            '[title*="New chat" i]', 'button[aria-label*="New topic" i]',
            '[aria-label*="Start new" i]', '[data-testid*="new-chat" i]',
            'button[aria-label*="New" i]',
        ]
        for sel in sels:
            for b in (_safe(lambda s=sel: driver.find_elements(By.CSS_SELECTOR, s)) or []):
                try:
                    if b.is_displayed() and b.is_enabled():
                        b.click()
                        time.sleep(1.5)
                        print(f"[engine] new chat via {sel}", flush=True)
                        on_log("Started a new Copilot chat.")
                        return True
                except Exception:
                    continue
        print("[engine] NO new-chat button found", flush=True)
        return False

    def close(self) -> None:
        if self._driver is not None:
            _safe(self._driver.quit)
            self._driver = None

    def is_open(self) -> bool:
        return self._driver is not None and _safe(lambda: self._driver.title) is not None

    def current_url(self, wait_conversation: bool = False, timeout: int = 12) -> str:
        """The live conversation URL (for 'continue this chat'). M365 Copilot rewrites the URL
        to /chat/conversation/<id> a few seconds AFTER the answer finishes, so optionally poll
        until that id appears."""
        if self._driver is None:
            return ""
        if not wait_conversation:
            return _safe(lambda: self._driver.current_url) or ""
        end, last = time.time() + timeout, ""
        while time.time() < end:
            last = _safe(lambda: self._driver.current_url) or ""
            if "conversation/" in last:
                return last
            time.sleep(1)
        return last

    def _ensure_driver(self, on_log: Callable[[str], None]):
        """A live driver WITHOUT starting a new chat (for resuming a specific conversation URL)."""
        d = self._driver
        if d is not None and _safe(lambda: d.current_url):
            return d
        return self._fresh(on_log)

    def _set_mode(self, driver, mode: str, on_log: Callable[[str], None]) -> None:
        """Click the Work|Web toggle so grounding matches the job (work=tenant, web=public)."""
        from selenium.webdriver.common.by import By
        sel = _MODE_TOGGLE.get((mode or "work").lower())
        if not sel:
            return
        for b in (_safe(lambda: driver.find_elements(By.CSS_SELECTOR, sel)) or []):
            try:
                if b.is_displayed() and b.is_enabled():
                    b.click()
                    time.sleep(1.0)
                    print(f"[s{self.idx}] mode → {mode}", flush=True)
                    on_log(f"Copilot mode: {mode}")
                    return
            except Exception:
                continue

    def _ready(self, on_log: Callable[[str], None]):
        """Get a usable driver for a new job: REUSE the live window (just start a New chat —
        much faster than relaunching), or open a fresh one if there's no live session."""
        d = self._driver
        if d is not None and _safe(lambda: d.current_url):
            self._new_chat(d, on_log)  # clean conversation, same window
            return d
        return self._fresh(on_log)

    # ---- inference ----
    def ask(self, prompt: str, on_log: Callable[[str], None] = print, timeout: int = 420,
            mode: str = "work", accept=None) -> str:
        if _engine_disabled():
            on_log(_ENGINE_DISABLED_MSG)
            return _ENGINE_DISABLED_MSG
        with self._lock:
            driver = self._ready(on_log)
            self._set_mode(driver, mode, on_log)
            return self._turn(driver, prompt, on_log, timeout, accept)

    def ask_chain(self, prompts: list[str], on_log: Callable[[str], None] = print,
                  timeout: int = 420, mode: str = "work") -> str:
        """Run several prompts as sequential turns in ONE Copilot conversation. Collects EVERY
        turn's answer and returns the LAST non-refusal, non-empty one — so a Copilot guardrail
        refusal on a later turn can never bury the real data from an earlier turn."""
        if _engine_disabled():
            on_log(_ENGINE_DISABLED_MSG)
            return _ENGINE_DISABLED_MSG
        with self._lock:
            driver = self._ready(on_log)  # one window + New chat for the whole chain
            self._set_mode(driver, mode, on_log)
            answers = []
            for n, prompt in enumerate(prompts, 1):
                on_log(f"Turn {n}/{len(prompts)}…")
                a = self._turn(driver, prompt, on_log, timeout)
                if _is_refusal(a):
                    on_log("Copilot refused that turn — keeping the prior good answer.")
                    a = ""
                answers.append(a)
            good = [a for a in answers if a and a.strip()]
            return good[-1] if good else ""

    def ask_chain_all(self, prompts: list[str], on_log: Callable[[str], None] = print,
                      timeout: int = 420, mode: str = "work", accept=None) -> list[str]:
        """Like ask_chain, but returns EVERY turn's answer (refusals → "") so a chunked feed +
        several extraction turns over the accumulated context can each be read. Used by the ATP
        generator: feed ~20K-char trip-report chunks, then ask for technologies/overview/contacts."""
        if _engine_disabled():
            on_log(_ENGINE_DISABLED_MSG)
            return ["" for _ in prompts]
        with self._lock:
            driver = self._ready(on_log)
            self._set_mode(driver, mode, on_log)
            answers = []
            for n, prompt in enumerate(prompts, 1):
                on_log(f"Turn {n}/{len(prompts)}…")
                a = self._turn(driver, prompt, on_log, timeout, accept)
                answers.append("" if _is_refusal(a) else a)
            return answers

    def ask_at(self, url: str, prompt: str, on_log: Callable[[str], None] = print,
               timeout: int = 420, mode: str = "work") -> str:
        """Resume an EXISTING Copilot conversation: navigate the driver to its URL (loading the
        prior context), then ask a follow-up turn. Used to continue a saved chat artifact."""
        if _engine_disabled():
            on_log(_ENGINE_DISABLED_MSG)
            return _ENGINE_DISABLED_MSG
        with self._lock:
            driver = self._ensure_driver(on_log)  # NO new chat — we navigate to the saved thread
            on_log("Resuming the saved conversation…")
            _safe(lambda: driver.get(url))
            time.sleep(4)                         # let the thread + composer load
            self._set_mode(driver, mode, on_log)
            return self._turn(driver, prompt, on_log, timeout)

    def _turn(self, driver, prompt: str, on_log: Callable[[str], None], timeout: int,
              accept=None) -> str:
        """One question→answer turn against the CURRENT conversation (no new window/chat)."""
        from selenium.webdriver.common.keys import Keys

        self._stop.clear()                       # fresh turn — clear any stale cancel signal
        one_line = " ".join((prompt + _SENTINEL_HINT).splitlines()).strip()

        box, end = None, time.time() + 60
        while box is None and time.time() < end:
            if self._stop.is_set():
                raise RuntimeError("cancelled by user")
            box = self._find_input(driver)
            if box is None:
                time.sleep(1)
        if box is None:
            # Likely a sign-in/redirect is blocking — surface the (minimized) window so the user can act.
            _safe(lambda: driver.set_window_position(80, 60))
            _safe(driver.maximize_window)
            on_log("⚠️ Couldn't find Copilot's input — sign in to M365 in the Chrome window that just opened, then retry.")
            return ""

        _safe(box.click)
        # Clear any residual text in the composer so we don't append to a stale prompt.
        existing = (_safe(lambda: box.get_attribute("value")) or _safe(lambda: box.text) or "")
        if existing.strip():
            print(f"[engine] composer had residual text: {existing[:80]!r}", flush=True)
        try:
            box.send_keys(Keys.CONTROL, "a")
            box.send_keys(Keys.DELETE)
        except Exception:
            pass
        time.sleep(0.2)
        self._type(box, one_line)
        time.sleep(0.5)
        baseline = self._answer_set(driver)  # answers already on the page (incl. prior turns) to ignore
        how = self._submit(driver, box)
        on_log(f"Submitted to Copilot (via {how}).")
        return self._wait_answer(driver, on_log, timeout, baseline, accept)

    def _type(self, box, text: str) -> None:
        """Enter the prompt. Short prompts are typed; LARGE prompts (e.g. pasted trip reports)
        are put on the clipboard and pasted with Ctrl+V — typing 20k+ chars char-by-char blows
        past Selenium's command timeout."""
        from selenium.webdriver.common.keys import Keys
        if len(text) <= 2000:
            box.send_keys(text)
            return
        try:
            import win32clipboard
            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
            win32clipboard.CloseClipboard()
            box.send_keys(Keys.CONTROL, "v")
            print(f"[engine] pasted {len(text):,} chars", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[engine] paste failed ({e}); typing in chunks", flush=True)
            for i in range(0, len(text), 800):
                box.send_keys(text[i:i + 800])

    def _block_texts2(self, driver) -> list:
        return [(_safe(lambda e=e: e.text) or "") for e in self._answer_blocks(driver)]

    @staticmethod
    def _extract(text: str) -> str:
        """The answer is the text AFTER 'Copilot said:' (drop the echoed prompt + 'Copilot' line)."""
        ans = text.split("Copilot said:")[-1]
        lines = ans.lstrip().split("\n")
        if lines and lines[0].strip().lower() == "copilot":
            lines = lines[1:]
        return "\n".join(lines).strip()

    @staticmethod
    def _clean(ans: str) -> str:
        """Trim trailing UI cruft and strip citation markers / hyperlinks (user wants none)."""
        for m in ("\nbing\n", "\nbing", "\nSources", "\nSearch results", "\nAI-generated content"):
            i = ans.find(m)
            if i != -1:
                ans = ans[:i]
        ans = re.sub(r"^\s*Reasoning completed in \d+ steps?\.?\s*", "", ans)  # reasoning header
        ans = re.sub(r"\[\d+\]\([^)]*\)", "", ans)          # numeric citation links [1](url)
        ans = re.sub(r"\[([^\]\n]+)\]\([^)]*\)", r"\1", ans)  # other md links -> text
        ans = re.sub(r"\[\d+\]", "", ans)                    # bare [1] citations
        ans = re.sub(r"https?://\S+", "", ans)               # stray bare URLs
        return ans.strip()

    def _answer_set(self, driver) -> set:
        """Answers already on the page before this turn (to exclude). Mirrors _best_answer:
        both 'Copilot said:' and clean blocks, minus the echoed prompt."""
        out = set()
        for t in self._block_texts2(driver):
            a = self._extract(t) if "Copilot said:" in t else (t or "").strip()
            if not a:
                continue
            head = a[:24].lower()
            if head.startswith(("you said:", "today\nyou said:")) or "you said:" in head:
                continue
            out.add(a)
        return out

    def _best_answer(self, driver, baseline: set) -> str:
        """Newest fresh answer. Considers both 'Copilot said:' blocks AND clean answer blocks
        (Web mode renders the finished answer in a block with NO 'Copilot said:' prefix),
        excludes the echoed prompt, and prefers a block that already carries the completion
        marker. DOM order → newest wins, so a multi-turn chain still grabs the current turn."""
        newest_marked, newest_any = "", ""
        for t in self._block_texts2(driver):
            a = self._extract(t) if "Copilot said:" in t else (t or "").strip()
            if not a or a in baseline:
                continue
            head = a[:24].lower()
            if head.startswith(("you said:", "today\nyou said:")) or "you said:" in head:
                continue  # the echoed prompt, not an answer
            if _ECHO_SIG in a.lower():
                continue  # our echoed prompt (carries the sentinel instruction) — never an answer
            newest_any = a
            if SENTINEL in a:
                newest_marked = a
        return newest_marked or newest_any

    def _submit(self, driver, box) -> str:
        """Click the real Send button (exact aria/class — never a 'Sendero' chip); Enter fallback."""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys

        for sel in _SEND_SELECTORS:
            for b in (_safe(lambda s=sel: driver.find_elements(By.CSS_SELECTOR, s)) or []):
                try:
                    if b.is_displayed() and b.is_enabled():
                        b.click()
                        print(f"[engine] clicked Send ({sel})", flush=True)
                        return "Send button"
                except Exception:
                    continue
        _safe(lambda: box.send_keys(Keys.ENTER))
        return "Enter (fallback)"

    def _find_input(self, driver):
        from selenium.webdriver.common.by import By

        cands = []
        for sel in _INPUT_SELECTORS:
            cands += _safe(lambda: driver.find_elements(By.CSS_SELECTOR, sel)) or []
        vis = [e for e in cands if _safe(lambda: e.is_displayed() and e.is_enabled())]
        if not vis:
            return None
        return max(vis, key=lambda e: _safe(lambda: e.location.get("y", 0)) or 0)

    def _answer_blocks(self, driver):
        from selenium.webdriver.common.by import By

        for sel in _ANSWER_SELECTORS:
            els = _safe(lambda: driver.find_elements(By.CSS_SELECTOR, sel)) or []
            if els:
                return els
        return []

    @staticmethod
    def _best_text(els) -> str:
        """The actual answer is the LONGEST block (avoids trailing toolbars/empty nodes)."""
        best = ""
        for e in els:
            t = (_safe(lambda e=e: e.text) or "").strip()
            if len(t) > len(best):
                best = t
        return best

    @staticmethod
    def _is_real(text: str) -> bool:
        tl = text.lower().strip()
        if len(tl) < 80:
            return False
        return not any(p in tl[:50] for p in _LOADING)

    @staticmethod
    def _is_loading(text: str) -> bool:
        """A short block that is just Copilot's 'Lining things up...' style placeholder."""
        tl = text.lower().strip()
        return len(tl) < 80 and any(p in tl for p in _LOADING)

    def _wait_answer(self, driver, on_log, timeout, baseline=None, accept=None) -> str:
        """Completion is primarily signalled by the SENTINEL marker (the safe, unambiguous done
        signal for free prose). For STRUCTURED outputs an optional `accept(text)` predicate may
        also complete the wait — but only once the answer is BOTH accepted AND stable for a few
        seconds (e.g. a parseable, closed JSON array), which can't be faked by streaming chatter.
        Web Copilot is inconsistent about emitting the marker, so this lets JSON tasks finish."""
        baseline = baseline or set()
        on_log("Waiting for Copilot to finish (watching for the completion marker)…")
        end = time.time() + timeout
        best, beat = "", time.time()
        acc_last, acc_stable = "", 0
        while time.time() < end:
            if self._stop.is_set():
                raise RuntimeError("cancelled by user")
            cur = self._best_answer(driver, baseline)
            if len(cur) > len(best):
                best = cur
            if SENTINEL in cur:               # primary, unambiguous done signal
                final = self._clean(cur.replace(SENTINEL, ""))
                on_log(f"✅ Completion marker found — captured {len(final):,} chars.")
                return final
            if accept and cur and len(cur) > 2:
                ok = False
                try:
                    ok = bool(accept(cur))
                except Exception:
                    ok = False
                if ok and cur == acc_last:
                    acc_stable += 1
                    if acc_stable >= 3:        # ~5s of a stable, validated-complete answer
                        final = self._clean(cur.replace(SENTINEL, ""))
                        on_log(f"✅ Answer validated complete — captured {len(final):,} chars.")
                        return final
                else:
                    acc_stable, acc_last = (0, cur) if ok else (0, "")
            if time.time() - beat >= 12:
                on_log(f"   …still composing ({len(best):,} chars).")
                beat = time.time()
            time.sleep(1.5)
        # Timed out with NO completion → do NOT save partial/streaming text.
        on_log("⚠️ Copilot never signalled completion — treating the answer as incomplete.")
        return ""

    @staticmethod
    def _strip_echo(text: str) -> str:
        """Drop the echoed prompt header ('You said: … Copilot said:') if present."""
        if not text:
            return text
        if "Copilot said:" in text:
            text = text.split("Copilot said:")[-1]
        lines = text.lstrip().split("\n")
        if lines and lines[0].strip().lower() == "copilot":
            lines = lines[1:]
        return "\n".join(lines).strip()


# Backwards-compat alias (older imports referenced CopilotEngine).
CopilotEngine = Session
