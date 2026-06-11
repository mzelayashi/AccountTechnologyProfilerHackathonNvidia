"""Knowledge Drop — ingest files from vault/inbox, classify to an account, file them."""
from __future__ import annotations

import datetime
import shutil

import config
from atlas.artifacts.ingest import read_file
from atlas.engine.extract import extract_json
from atlas.store import vault

from .base import Skill, SkillResult, register

_CLASSIFY = (
    "Read this document excerpt and respond with ONLY a JSON object (no prose):\n"
    '{"account":"the customer/company this document is about (best guess)",'
    '"summary":"a 4-6 line summary","entities":"key people, technologies, and dates"}\n\n'
    "DOCUMENT:\n"
)


@register
class KnowledgeDrop(Skill):
    key = "knowledge_drop"
    name = "Knowledge Drop"
    icon = "📥"
    description = "Ingest files you drop in vault/inbox — auto-file them by account."
    inputs = []

    def run(self, ctx, ask, log) -> SkillResult:
        files = [p for p in config.INBOX_DIR.iterdir() if p.is_file()]
        if not files:
            return SkillResult(text=f"No files to ingest.\n\nDrop files into:\n{config.INBOX_DIR}")

        results = []
        for p in files:
            log(f"Reading {p.name}…")
            try:
                text = read_file(p)
            except Exception as e:  # noqa: BLE001
                log(f"  skipped {p.name}: {e}")
                continue
            if not text.strip():
                log(f"  {p.name}: no extractable text")
                continue

            log(f"  classifying {p.name} on Nemotron…")
            data = extract_json(ask(_CLASSIFY + text[:6000])) or {}
            account = (data.get("account") or "Unsorted").strip() or "Unsorted"
            summary = data.get("summary") or text[:400]

            adir = vault.account_dir(account)
            rec = (f"# {p.name}\n\n- Account: {account}\n- Ingested: "
                   f"{datetime.date.today().isoformat()}\n\n## Summary\n{summary}\n\n"
                   f"## Entities\n{data.get('entities', '')}\n")
            vault.write_text(adir / "sources" / (p.stem + ".md"), rec)

            acc = vault.load_account(account)
            acc.setdefault("sources", [])
            if p.name not in acc["sources"]:
                acc["sources"].append(p.name)
            vault.save_account(account, acc)

            try:
                shutil.move(str(p), str(config.INBOX_PROCESSED / p.name))
            except Exception:
                pass
            results.append(f"• {p.name}  →  {account}")
            log(f"  filed under {account}")

        return SkillResult(
            text="Ingested:\n" + "\n".join(results) if results else "Nothing ingested.")
