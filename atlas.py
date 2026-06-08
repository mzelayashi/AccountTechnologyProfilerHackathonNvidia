"""SHI ATLAS — Jarvis-style desktop OS for a solutions engineer.

Launch:  python atlas.py   (or START.bat)
"""
from __future__ import annotations

import datetime
import threading
import tkinter as tk
from tkinter import ttk

import config
from atlas.engine import get_engine
from atlas.skills import all_skills, get_skill
from src.ui_desktop import theme
from src.ui_desktop.theme import COLORS, FONT, MONO

APP_TITLE = "SHI ATLAS"


def _greeting() -> str:
    h = datetime.datetime.now().hour
    part = "morning" if h < 12 else "afternoon" if h < 18 else "evening"
    return f"Good {part}, {config.USER_NAME}"


def _today_long() -> str:
    return datetime.datetime.now().strftime("%A, %B %d, %Y")


def _loading_html(msg: str) -> str:
    import html as _h
    return ("<body style='margin:0;background:#0b0f17;color:#8b949e;font-family:Segoe UI'>"
            "<div style='padding:48px;font-size:15px'><span style='color:#56d4dd;font-weight:700;"
            f"letter-spacing:3px'>◆ SHI ATLAS</span><br><br>{_h.escape(msg)}</div></body>")


def _meeting_html(card: dict) -> str:
    import html as _h
    body = "<br>".join(_h.escape(line) for line in card.get("body", "").splitlines())
    return ("<body style='margin:0;background:#0b0f17;color:#e6edf3;font-family:Segoe UI'>"
            "<div style='padding:24px;max-width:920px'>"
            f"<h2 style='color:#56d4dd;margin-top:0'>{_h.escape(card.get('title', ''))}</h2>"
            f"<div style='line-height:1.6;font-size:14px;color:#c9d4e0'>{body}</div></div></body>")


class Atlas:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.engine = get_engine()
        root.title(APP_TITLE)
        root.geometry("1180x780")
        root.minsize(960, 640)
        root.configure(bg=COLORS["bg_primary"])
        theme.apply_dark_titlebar(root)
        theme.style_ttk(root)
        root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_header()
        self.main = tk.Frame(root, bg=COLORS["bg_primary"])
        self.main.pack(fill="both", expand=True, padx=22, pady=(0, 16))
        self.show_welcome()

    # ---------- chrome ----------
    def _build_header(self) -> None:
        bar = tk.Frame(self.root, bg=COLORS["bg_secondary"], height=60)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        tk.Label(bar, text="◆ SHI ATLAS", bg=COLORS["bg_secondary"],
                 fg=COLORS["accent_cyan"], font=(FONT, 15, "bold")).pack(side="left", padx=20)
        tk.Label(bar, text="powered by your Microsoft 365 Copilot", bg=COLORS["bg_secondary"],
                 fg=COLORS["text_muted"], font=(FONT, 9)).pack(side="left")
        theme.button(bar, "Skills", self.show_launcher, width=10).pack(side="right", padx=8, pady=12)
        theme.button(bar, "Home", self.show_welcome, width=8).pack(side="right", pady=12)

    def _clear(self) -> None:
        for w in self.main.winfo_children():
            w.destroy()

    def _on_close(self) -> None:
        try:
            self.engine.close()
        except Exception:
            pass
        self.root.destroy()

    # ---------- welcome / daily briefing ----------
    def show_welcome(self) -> None:
        self._clear()
        row = tk.Frame(self.main, bg=COLORS["bg_primary"])
        row.pack(anchor="w", pady=(8, 4))
        theme.button(row, "↻ Refresh brief", lambda: self._run_daily(force=True),
                     width=15).pack(side="left", padx=(0, 8))
        theme.button(row, "⛶ Full dashboard", self._open_dashboard_browser,
                     width=16).pack(side="left", padx=(0, 8))
        theme.button(row, "Open Skills →", self.show_launcher,
                     color=COLORS["accent_primary"], width=14).pack(side="left")

        self.brief_meetings = []
        self.html_view = self._make_html(self.main)
        if self.html_view is not None:
            self.html_view.pack(fill="both", expand=True, pady=(6, 0))
            self._load_html(self.html_view, _loading_html("Preparing your day…"))
            self.cards_area = None
        else:
            self.cards_area = tk.Frame(self.main, bg=COLORS["bg_primary"])
            self.cards_area.pack(fill="both", expand=True)
        self._run_daily()

    def _make_html(self, parent):
        try:
            from tkinterweb import HtmlFrame

            f = HtmlFrame(parent, messages_enabled=False)
            try:
                f.on_link_click(self._on_link)
            except Exception:
                pass
            return f
        except Exception as e:  # noqa: BLE001
            print(f"[atlas] tkinterweb unavailable ({e}); using basic cards.", flush=True)
            return None

    def _load_html(self, frame, html_str: str) -> None:
        try:
            frame.load_html(html_str)
        except Exception as e:  # noqa: BLE001
            print(f"[atlas] load_html failed: {e}", flush=True)

    def _on_link(self, url: str) -> None:
        if url and url.startswith("atlas:meeting:"):
            try:
                self._show_card(self.brief_meetings[int(url.rsplit(":", 1)[-1])])
            except Exception:
                pass

    def _run_daily(self, force: bool = False) -> None:
        if not force:
            from atlas.skills.base import SkillResult
            from atlas.skills.daily_briefing import load_today

            cached = load_today()
            if cached:
                self._render_cards(SkillResult(cards=cached))
                return

        if self.html_view is not None:
            self._load_html(self.html_view, _loading_html("Preparing your day… asking Copilot…"))

        def log(msg: str) -> None:
            print(f"[brief] {msg}", flush=True)

        def worker() -> None:
            ask = lambda p: self.engine.ask(p, on_log=log)  # noqa: E731
            try:
                result = get_skill("daily_briefing").run({}, ask, log)
            except Exception as e:  # noqa: BLE001
                self.root.after(0, lambda: self._dash_error(str(e)))
                return
            self.root.after(0, lambda: self._render_cards(result))

        threading.Thread(target=worker, daemon=True).start()

    def _dash_error(self, msg: str) -> None:
        if self.html_view is not None:
            self._load_html(self.html_view, _loading_html(f"Couldn't load briefing: {msg}"))

    def _render_cards(self, result) -> None:
        self.brief_meetings = result.cards or []
        if self.html_view is not None:
            from atlas.artifacts import dashboard_html

            self._dashboard_html = dashboard_html.render(
                _greeting(), _today_long(), self.brief_meetings)
            self._load_html(self.html_view, self._dashboard_html)
            return

        # Tk fallback (no tkinterweb)
        for w in self.cards_area.winfo_children():
            w.destroy()
        canvas = tk.Canvas(self.cards_area, bg=COLORS["bg_primary"], highlightthickness=0)
        sb = ttk.Scrollbar(self.cards_area, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=COLORS["bg_primary"])
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw", width=1080)
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        for card in self.brief_meetings:
            f = tk.Frame(inner, bg=COLORS["bg_secondary"], cursor="hand2",
                         highlightbackground=COLORS["border"], highlightthickness=1)
            f.pack(fill="x", pady=5, padx=2)
            tk.Label(f, text=card["title"], bg=COLORS["bg_secondary"], fg=COLORS["text_primary"],
                     font=(FONT, 12, "bold"), anchor="w", justify="left", wraplength=1020).pack(
                anchor="w", padx=12, pady=(8, 2))
            preview = (card["body"][:140] + "…") if len(card["body"]) > 140 else card["body"]
            tk.Label(f, text=preview, bg=COLORS["bg_secondary"], fg=COLORS["text_secondary"],
                     font=(FONT, 9), anchor="w", justify="left", wraplength=1020).pack(
                anchor="w", padx=12, pady=(0, 8))
            for w in (f, *f.winfo_children()):
                w.bind("<Button-1>", lambda e, c=card: self._show_card(c))

    def _open_dashboard_browser(self) -> None:
        html_str = getattr(self, "_dashboard_html", None)
        if not html_str:
            return
        import webbrowser

        p = config.RUNS_DIR / "dashboard.html"
        p.write_text(html_str, encoding="utf-8")
        webbrowser.open(p.as_uri())

    def _show_card(self, card: dict) -> None:
        self._clear()
        top = tk.Frame(self.main, bg=COLORS["bg_primary"])
        top.pack(fill="x", pady=(12, 6))
        tk.Label(top, text=card["title"], bg=COLORS["bg_primary"], fg=COLORS["text_primary"],
                 font=(FONT, 16, "bold"), wraplength=900, justify="left").pack(side="left")
        theme.button(top, "← Back", self.show_welcome, width=10).pack(side="right")
        view = self._make_html(self.main)
        if view is not None:
            view.pack(fill="both", expand=True, pady=6)
            self._load_html(view, _meeting_html(card))
        else:
            box = tk.Text(self.main, bg=COLORS["bg_secondary"], fg=COLORS["text_primary"],
                          font=(FONT, 11), wrap="word", relief="flat")
            box.insert("1.0", card["body"])
            box.configure(state="disabled")
            box.pack(fill="both", expand=True, pady=6)

    # ---------- skills launcher ----------
    def show_launcher(self) -> None:
        self._clear()
        tk.Label(self.main, text="Skills", bg=COLORS["bg_primary"], fg=COLORS["text_primary"],
                 font=(FONT, 20, "bold")).pack(anchor="w", pady=(20, 12))
        grid = tk.Frame(self.main, bg=COLORS["bg_primary"])
        grid.pack(fill="both", expand=True)
        skills = all_skills()
        cols = 3
        for i, sk in enumerate(skills):
            r, c = divmod(i, cols)
            card = tk.Frame(grid, bg=COLORS["bg_secondary"], cursor="hand2", width=340, height=120,
                            highlightbackground=COLORS["border"], highlightthickness=1)
            card.grid(row=r, column=c, padx=8, pady=8, sticky="nsew")
            card.pack_propagate(False)
            tk.Label(card, text=f"{sk.icon}  {sk.name}", bg=COLORS["bg_secondary"],
                     fg=COLORS["text_primary"], font=(FONT, 13, "bold")).pack(anchor="w", padx=12, pady=(12, 2))
            tk.Label(card, text=sk.description, bg=COLORS["bg_secondary"], fg=COLORS["text_secondary"],
                     font=(FONT, 9), wraplength=300, justify="left").pack(anchor="w", padx=12)
            for w in (card, *card.winfo_children()):
                w.bind("<Button-1>", lambda e, s=sk: self.open_skill(s))
        for c in range(cols):
            grid.columnconfigure(c, weight=1)

    # ---------- run a skill ----------
    def open_skill(self, skill) -> None:
        self._clear()
        top = tk.Frame(self.main, bg=COLORS["bg_primary"])
        top.pack(fill="x", pady=(16, 6))
        tk.Label(top, text=f"{skill.icon}  {skill.name}", bg=COLORS["bg_primary"],
                 fg=COLORS["text_primary"], font=(FONT, 17, "bold")).pack(side="left")
        theme.button(top, "← Skills", self.show_launcher, width=10).pack(side="right")
        tk.Label(self.main, text=skill.description, bg=COLORS["bg_primary"],
                 fg=COLORS["text_muted"], font=(FONT, 10)).pack(anchor="w", pady=(0, 12))

        entries: dict[str, tk.Entry] = {}
        for fld in skill.inputs:
            tk.Label(self.main, text=fld.label, bg=COLORS["bg_primary"], fg=COLORS["text_secondary"],
                     font=(FONT, 10)).pack(anchor="w")
            e = tk.Entry(self.main, width=80, font=(FONT, 12), bg=COLORS["bg_tertiary"],
                         fg=COLORS["text_primary"], insertbackground=COLORS["text_primary"], relief="flat")
            e.pack(ipady=6, pady=(0, 10), anchor="w", fill="x")
            if fld.placeholder:
                e.insert(0, fld.placeholder)
                e.bind("<FocusIn>", lambda ev, en=e, ph=fld.placeholder:
                       en.delete(0, "end") if en.get() == ph else None)
            entries[fld.key] = e

        theme.button(self.main, f"Run {skill.name}",
                     lambda: self._exec_skill(skill, {k: v.get().strip() for k, v in entries.items()}),
                     color=COLORS["accent_primary"], width=24, big=True).pack(anchor="w", pady=4)

    def _exec_skill(self, skill, ctx: dict) -> None:
        # strip placeholders that weren't edited
        for fld in skill.inputs:
            if ctx.get(fld.key) == fld.placeholder:
                ctx[fld.key] = ""
        self._clear()
        tk.Label(self.main, text=f"{skill.icon}  {skill.name}", bg=COLORS["bg_primary"],
                 fg=COLORS["text_primary"], font=(FONT, 16, "bold")).pack(anchor="w", pady=(14, 6))
        log = tk.Text(self.main, bg=COLORS["bg_secondary"], fg=COLORS["text_secondary"],
                      font=(MONO, 10), wrap="word", height=10, relief="flat")
        log.pack(fill="x", pady=4)
        log.configure(state="disabled")
        theme.button(self.main, "← Skills", self.show_launcher, width=10).pack(anchor="w", pady=6)

        def out(msg: str) -> None:
            self.root.after(0, lambda: self._log(log, msg))

        def worker() -> None:
            ask = lambda p: self.engine.ask(p, on_log=out)  # noqa: E731
            try:
                result = skill.run(ctx, ask, out)
            except Exception as e:  # noqa: BLE001
                out(f"Error: {e}")
                return
            self.root.after(0, lambda: self._show_result(skill, result))

        threading.Thread(target=worker, daemon=True).start()

    def _show_result(self, skill, result) -> None:
        self._clear()
        top = tk.Frame(self.main, bg=COLORS["bg_primary"])
        top.pack(fill="x", pady=(14, 6))
        tk.Label(top, text=f"{skill.icon}  {skill.name}", bg=COLORS["bg_primary"],
                 fg=COLORS["text_primary"], font=(FONT, 16, "bold")).pack(side="left")
        theme.button(top, "← Skills", self.show_launcher, width=10).pack(side="right")

        if result.files:
            tk.Label(self.main, text="Saved: " + ", ".join(str(p.name) for p in result.files),
                     bg=COLORS["bg_primary"], fg=COLORS["text_muted"], font=(FONT, 9)).pack(anchor="w")

        box = tk.Text(self.main, bg=COLORS["bg_secondary"], fg=COLORS["text_primary"],
                      font=(FONT, 11), wrap="word", relief="flat")
        box.insert("1.0", result.text or "(no text)")
        box.configure(state="disabled")
        box.pack(fill="both", expand=True, pady=6)

        if result.diagram_html:
            import webbrowser
            theme.button(self.main, "🗺 Open diagram",
                         lambda: webbrowser.open(result.diagram_html.as_uri()),
                         color=COLORS["accent_purple"], width=18).pack(anchor="w", pady=6)

    def _log(self, widget: tk.Text, msg: str) -> None:
        widget.configure(state="normal")
        widget.insert("end", msg + "\n")
        widget.see("end")
        widget.configure(state="disabled")
        try:
            print(f"[atlas] {msg}", flush=True)
        except Exception:
            pass


def main() -> None:
    root = tk.Tk()
    Atlas(root)
    root.mainloop()


if __name__ == "__main__":
    main()
