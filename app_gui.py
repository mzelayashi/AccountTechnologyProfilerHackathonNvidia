"""Customer Meeting Insight — clickable desktop app (Tkinter, ATPtool-style).

Flow: Home → "Grab meeting from OneDrive" opens Chrome (your own login) → you
download a transcript → it's parsed and analyzed → Analysis screen shows summary,
what the customer wants, and action items.

Run:  python app_gui.py   (or START.bat)
"""
from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

import config
from src.browser.grab import grab_transcript
from src.transcript.parse import parse_transcript
from src.ui_desktop import theme
from src.ui_desktop.theme import COLORS, FONT, MONO

APP_TITLE = "Customer Meeting Insight"


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title(APP_TITLE)
        root.geometry("1100x740")
        root.minsize(900, 600)
        root.configure(bg=COLORS["bg_primary"])
        theme.apply_dark_titlebar(root)
        theme.style_ttk(root)

        self.customer = tk.StringVar()
        self.question = tk.StringVar()
        self._build_header()
        self.main = tk.Frame(root, bg=COLORS["bg_primary"])
        self.main.pack(fill="both", expand=True, padx=20, pady=(0, 16))
        self.show_home()

    # ---------- chrome / header ----------
    def _build_header(self) -> None:
        bar = tk.Frame(self.root, bg=COLORS["bg_secondary"], height=64)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        tk.Label(
            bar, text="📊  Customer Meeting Insight", bg=COLORS["bg_secondary"],
            fg=COLORS["text_primary"], font=(FONT, 15, "bold"),
        ).pack(side="left", padx=20)
        tk.Label(
            bar, text="grab a meeting transcript from OneDrive → analyze it",
            bg=COLORS["bg_secondary"], fg=COLORS["text_muted"], font=(FONT, 10),
        ).pack(side="left", padx=4)

    def _clear(self) -> None:
        for w in self.main.winfo_children():
            w.destroy()

    # ---------- screens ----------
    def show_home(self) -> None:
        self._clear()
        wrap = tk.Frame(self.main, bg=COLORS["bg_primary"])
        wrap.pack(expand=True, fill="x")

        tk.Label(
            wrap, text="Ask your Copilot", bg=COLORS["bg_primary"],
            fg=COLORS["text_primary"], font=(FONT, 20, "bold"),
        ).pack(pady=(40, 4))
        tk.Label(
            wrap, text="The tool types your question into Microsoft 365 Copilot and brings the answer back.",
            bg=COLORS["bg_primary"], fg=COLORS["text_muted"], font=(FONT, 10),
        ).pack(pady=(0, 16))

        q = tk.Entry(
            wrap, textvariable=self.question, width=64, font=(FONT, 13),
            bg=COLORS["bg_tertiary"], fg=COLORS["text_primary"],
            insertbackground=COLORS["text_primary"], relief="flat",
        )
        q.pack(ipady=10, pady=(0, 12))
        placeholder = "e.g. tell me about the current initiatives for AWC from the last meetings"
        q.insert(0, placeholder)
        q.bind("<FocusIn>", lambda e: q.delete(0, "end") if q.get() == placeholder else None)
        q.bind("<Return>", lambda e: self.start_ask())

        theme.button(
            wrap, "🟣  Ask Copilot", self.start_ask,
            color=COLORS["accent_purple"], width=30, big=True,
        ).pack(pady=6)

        tk.Label(
            wrap, text="— or work from a specific meeting file —", bg=COLORS["bg_primary"],
            fg=COLORS["text_muted"], font=(FONT, 9),
        ).pack(pady=(26, 10))

        row = tk.Frame(wrap, bg=COLORS["bg_primary"])
        row.pack()
        theme.button(row, "🌐  Grab from OneDrive", self.start_grab, width=22).pack(side="left", padx=6)
        theme.button(row, "📂  Open a file", self.open_local_file, width=18).pack(side="left", padx=6)

        if config.LLM_PROVIDER in ("anthropic", "azure_openai"):
            note = f"Engine: {config.LLM_PROVIDER} (API)."
        else:
            note = "Engine: your Microsoft 365 Copilot in the browser — no API key, no tokens."
        tk.Label(
            wrap, text=note, bg=COLORS["bg_primary"], fg=COLORS["text_muted"],
            font=(FONT, 9), wraplength=560,
        ).pack(pady=(24, 0))

    def start_ask(self) -> None:
        question = self.question.get().strip()
        if not question or question.startswith("e.g. "):
            return
        log = self.show_progress()
        self._append(log, f"Asking Copilot: {question}")

        def out(msg: str) -> None:
            self.root.after(0, lambda: self._append(log, msg))

        def worker() -> None:
            try:
                from src.llm.copilot_browser import ask_copilot_question

                answer = ask_copilot_question(question, on_log=out)
            except Exception as e:  # noqa: BLE001
                out(f"Copilot automation error: {e}")
                answer = ""
            self.root.after(0, lambda: self.show_copilot_answer({}, answer, f'Copilot · "{question[:50]}"'))

        threading.Thread(target=worker, daemon=True).start()

    def show_progress(self) -> tk.Text:
        self._clear()
        tk.Label(
            self.main, text="Grabbing transcript…", bg=COLORS["bg_primary"],
            fg=COLORS["text_primary"], font=(FONT, 15, "bold"),
        ).pack(anchor="w", pady=(10, 8))
        log = tk.Text(
            self.main, bg=COLORS["bg_secondary"], fg=COLORS["text_secondary"],
            font=(MONO, 10), relief="flat", wrap="word", height=20,
        )
        log.pack(fill="both", expand=True)
        log.configure(state="disabled")
        theme.button(self.main, "← Back", self.show_home, width=12).pack(anchor="w", pady=10)
        return log

    def show_analysis(self, parsed: dict, result: dict | None, src_name: str) -> None:
        self._clear()
        top = tk.Frame(self.main, bg=COLORS["bg_primary"])
        top.pack(fill="x", pady=(8, 6))
        title = (result or {}).get("meeting_title") or src_name
        tk.Label(
            top, text=title, bg=COLORS["bg_primary"], fg=COLORS["text_primary"],
            font=(FONT, 16, "bold"),
        ).pack(side="left")
        theme.button(top, "← Home", self.show_home, width=10).pack(side="right")

        cust = self.customer.get().strip()
        meta = f"Customer: {cust or '—'}    Speakers: {len(parsed.get('speakers') or [])}    Source: {src_name}"
        tk.Label(
            self.main, text=meta, bg=COLORS["bg_primary"], fg=COLORS["text_muted"],
            font=(FONT, 9),
        ).pack(anchor="w", pady=(0, 10))

        canvas = tk.Canvas(self.main, bg=COLORS["bg_primary"], highlightthickness=0)
        scroll = ttk.Scrollbar(self.main, orient="vertical", command=canvas.yview)
        body = tk.Frame(canvas, bg=COLORS["bg_primary"])
        body.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=body, anchor="nw", width=1020)
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        if result is None:
            self._render_no_llm(body, parsed, src_name)
        else:
            self._render_result(body, parsed, result)

    # ---------- render helpers ----------
    def _section(self, parent, text):
        tk.Label(
            parent, text=text, bg=COLORS["bg_primary"], fg=COLORS["accent_cyan"],
            font=(FONT, 12, "bold"),
        ).pack(anchor="w", pady=(14, 4))

    def _para(self, parent, text):
        tk.Label(
            parent, text=text, bg=COLORS["bg_primary"], fg=COLORS["text_primary"],
            font=(FONT, 11), wraplength=1000, justify="left",
        ).pack(anchor="w", pady=2)

    def _render_result(self, parent, parsed, result):
        self._section(parent, "📝 Summary")
        self._para(parent, result.get("summary") or "—")

        self._section(parent, "🎯 What the customer wants us to focus on")
        focus = result.get("focus_areas") or []
        if not focus:
            self._para(parent, "—")
        for i, f in enumerate(focus, 1):
            box = tk.Frame(parent, bg=COLORS["bg_secondary"])
            box.pack(fill="x", pady=4)
            tk.Label(
                box, text=f"{i}. {f.get('item', '')}", bg=COLORS["bg_secondary"],
                fg=COLORS["text_primary"], font=(FONT, 11, "bold"), wraplength=980,
                justify="left",
            ).pack(anchor="w", padx=10, pady=(8, 0))
            if f.get("rationale"):
                tk.Label(
                    box, text=f.get("rationale"), bg=COLORS["bg_secondary"],
                    fg=COLORS["text_secondary"], font=(FONT, 10), wraplength=980,
                    justify="left",
                ).pack(anchor="w", padx=10)
            if f.get("citation"):
                tk.Label(
                    box, text=f"↳ {f.get('citation')}", bg=COLORS["bg_secondary"],
                    fg=COLORS["text_muted"], font=(FONT, 9), wraplength=980, justify="left",
                ).pack(anchor="w", padx=10, pady=(0, 8))

        self._section(parent, "✅ Action items")
        actions = result.get("action_items") or []
        if not actions:
            self._para(parent, "—")
        else:
            tv = ttk.Treeview(parent, columns=("a", "o", "d"), show="headings", height=min(len(actions), 8))
            for c, label, w in (("a", "Action", 640), ("o", "Owner", 160), ("d", "Due", 140)):
                tv.heading(c, text=label)
                tv.column(c, width=w)
            for it in actions:
                tv.insert("", "end", values=(it.get("text", ""), it.get("owner") or "", it.get("due_date") or ""))
            tv.pack(fill="x", pady=4)

    def _render_no_llm(self, parent, parsed, src_name):
        tk.Label(
            parent,
            text="No LLM key is set, so here's the parsed transcript. Click 'Copy transcript', "
            "paste it to Claude, and ask your question — or set a key in .env for in-app analysis.",
            bg=COLORS["bg_primary"], fg=COLORS["accent_warning"], font=(FONT, 10),
            wraplength=1000, justify="left",
        ).pack(anchor="w", pady=(4, 8))
        txt = tk.Text(parent, bg=COLORS["bg_secondary"], fg=COLORS["text_primary"], font=(MONO, 10), wrap="word", height=22)
        txt.insert("1.0", parsed.get("text") or "")
        txt.configure(state="disabled")
        txt.pack(fill="both", expand=True, pady=4)

        def copy():
            self.root.clipboard_clear()
            self.root.clipboard_append(parsed.get("text") or "")
        theme.button(parent, "📋 Copy transcript", copy, color=COLORS["accent_green"], width=20).pack(anchor="w", pady=8)

    # ---------- actions ----------
    def start_grab(self) -> None:
        log = self.show_progress()

        def out(msg: str) -> None:
            self.root.after(0, lambda: self._append(log, msg))

        def worker() -> None:
            path = grab_transcript(on_log=out)
            if path is None:
                out("No file captured. You can try again or use 'Open a downloaded file'.")
                return
            self.root.after(0, lambda: self._process_file(path))

        threading.Thread(target=worker, daemon=True).start()

    def open_local_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Pick a transcript",
            initialdir=str(config.DOWNLOAD_DIR),
            filetypes=[("Transcripts", "*.vtt *.docx *.txt"), ("All files", "*.*")],
        )
        if path:
            self._process_file(Path(path))

    def _process_file(self, path: Path) -> None:
        log = self.show_progress()
        self._append(log, f"Parsing {path.name}…")

        def worker() -> None:
            try:
                parsed = parse_transcript(path.name, path.read_bytes())
            except Exception as e:  # noqa: BLE001
                self.root.after(0, lambda: self._append(log, f"Parse error: {e}"))
                return
            if not parsed.get("text"):
                self.root.after(0, lambda: self._append(log, "Transcript appears empty."))
                return
            self.root.after(0, lambda: self._dispatch(parsed, path, log))

        threading.Thread(target=worker, daemon=True).start()

    def _dispatch(self, parsed: dict, path: Path, log: tk.Text) -> None:
        """On the main thread: route to the API engine or the Copilot-browser engine."""
        if config.LLM_PROVIDER in ("anthropic", "azure_openai"):
            self._append(log, f"Analyzing with {config.LLM_PROVIDER}…")

            def api_worker() -> None:
                try:
                    from src.llm.factory import get_provider
                    from src.llm.prompts import analyze_transcript

                    result = analyze_transcript(
                        get_provider(), parsed["text"], self.customer.get().strip() or None
                    )
                except Exception as e:  # noqa: BLE001
                    self.root.after(0, lambda: self._append(log, f"Analysis failed: {e}"))
                    return
                self.root.after(0, lambda: self.show_analysis(parsed, result, path.name))

            threading.Thread(target=api_worker, daemon=True).start()
            return

        # Default: Microsoft 365 Copilot in the browser (no API key / tokens).
        from src.llm.prompts import copilot_prompt

        prompt = copilot_prompt(parsed["text"], self.customer.get().strip() or None)
        self._append(log, "Opening your Microsoft 365 Copilot…")

        def out(msg: str) -> None:
            self.root.after(0, lambda: self._append(log, msg))

        def copilot_worker() -> None:
            try:
                from src.llm.copilot_browser import ask_copilot_question

                answer = ask_copilot_question(prompt, on_log=out)
            except Exception as e:  # noqa: BLE001
                out(f"Copilot automation error: {e}")
                answer = ""
            self.root.after(0, lambda: self.show_copilot_answer(parsed, answer, path.name))

        threading.Thread(target=copilot_worker, daemon=True).start()

    def show_copilot_answer(self, parsed: dict, answer: str, src_name: str) -> None:
        self._clear()
        top = tk.Frame(self.main, bg=COLORS["bg_primary"])
        top.pack(fill="x", pady=(8, 6))
        tk.Label(
            top, text="🟣 Copilot analysis", bg=COLORS["bg_primary"],
            fg=COLORS["text_primary"], font=(FONT, 16, "bold"),
        ).pack(side="left")
        theme.button(top, "← Home", self.show_home, width=10).pack(side="right")
        tk.Label(
            self.main, text=f"Source: {src_name}", bg=COLORS["bg_primary"],
            fg=COLORS["text_muted"], font=(FONT, 9),
        ).pack(anchor="w", pady=(0, 8))

        if answer:
            box = tk.Text(
                self.main, bg=COLORS["bg_secondary"], fg=COLORS["text_primary"],
                font=(FONT, 11), wrap="word", relief="flat",
            )
            box.insert("1.0", answer)
            box.configure(state="disabled")
            box.pack(fill="both", expand=True, pady=4)
        else:
            tk.Label(
                self.main,
                text="Copilot's answer is in the open Chrome window (auto-capture didn't grab it). "
                "The transcript + question were pasted in for you. You can copy the answer back "
                "here, or we can tune the capture next.",
                bg=COLORS["bg_primary"], fg=COLORS["accent_warning"], font=(FONT, 11),
                wraplength=1000, justify="left",
            ).pack(anchor="w", pady=8)

    def _append(self, log: tk.Text, msg: str) -> None:
        log.configure(state="normal")
        log.insert("end", msg + "\n")
        log.see("end")
        log.configure(state="disabled")
        # Mirror to stdout (captured to the run log) for debugging.
        try:
            print(f"[log] {msg}", flush=True)
        except Exception:
            pass


def main() -> None:
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
