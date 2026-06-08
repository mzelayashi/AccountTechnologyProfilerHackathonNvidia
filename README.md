# A.T.L.A.S. v1.0
### Autonomous Tactical Learning Agentic System

ATLAS is an operating system for a Solutions Architect. It pairs an **ontology-driven operating
picture** — every customer, meeting, technology, contact, and deliverable is a typed object linked into
one navigable model — with an **autonomous reasoning agent** that, from a single command box, interprets
intent, decomposes a goal, dispatches parallel work, and synthesizes the result. Its inference engine is
**your own Microsoft 365 Copilot, driven through a real browser** — no API keys, no tokens, no admin
scopes.

---

## Prerequisites
- **Windows 10 / 11**
- **Python 3.10 or newer** — https://www.python.org/downloads/ (tick *"Add Python to PATH"* during install)
- **Microsoft Edge** (WebView2, built into Windows 11) and **Google Chrome**
- A **licensed Microsoft 365 Copilot** account (your own work account)

## Quick start
1. **Double-click `setup.bat`** — once. Creates a local virtual environment and installs dependencies.
2. **Double-click `START.bat`** — launches ATLAS.
3. **Sign in on first run.** A Chrome window will surface asking you to sign in to Microsoft 365 — log
   in once; the session is remembered locally on *your* machine.

> Tip: in **Settings** you can toggle *"Show the Copilot Chrome windows"* to watch them work.

## What's in the box
- `atlas/` — the application (UI, brain, jobs, engine, skills, stores, ATP, Continual Suggestions)
- `atlas_web.py`, `config.py`, `requirements.txt`, `START.bat`, `setup.bat`
- `ATLAS_ARCHITECTURE.md` / `.drawio`, the Engineering PDF, and the User Guide PDF
- A **sample** People Resources directory so that feature works out of the box

## Data & privacy
Ships **clean**: no credentials, no Microsoft 365 session, no customer data. The vault is created empty
on first launch and fills only with what *you* generate locally. The People Resources directory is a
small **synthetic sample** — replace it via *People Resources → Import*. All data stays on your machine.

## Troubleshooting
- **"Python is not recognized"** — install Python 3.10+ and re-run `setup.bat` (tick *Add to PATH*).
- **A Chrome window opens and waits** — that's the Microsoft 365 sign-in; log in and the job continues.
- **A day's calendar looks thin** — click **↻ refresh** on the Calendar (Copilot occasionally needs a
  retry); the 3 days also auto-refresh every 30 minutes.
- **Want to stop a running task?** Click the **✕** on its chip in the *Working on* bar — it ends the
  task and closes the Chrome it was using.
- **Reset** — close ATLAS, delete the `vault/` and `cache/` folders, relaunch.

_ATLAS — Solutions Engineering. Internal tool; share responsibly._
