"""Read dropped files (.vtt/.docx/.txt/.pdf/.mht) into plain text for ingestion."""
from __future__ import annotations

import html as _html
import re
from pathlib import Path


def read_file(path: Path) -> str:
    ext = path.suffix.lower()
    data = path.read_bytes()
    if ext in (".vtt", ".docx", ".txt", ".text"):
        from src.transcript.parse import parse_transcript

        return parse_transcript(path.name, data).get("text", "")
    if ext == ".pdf":
        return _read_pdf(data)
    if ext in (".mht", ".mhtml"):
        return _read_mht(data)
    return data.decode("utf-8", errors="replace")


def _read_pdf(data: bytes) -> str:
    import io

    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n".join((page.extract_text() or "") for page in reader.pages).strip()


def _read_mht(data: bytes) -> str:
    import email

    msg = email.message_from_bytes(data)
    html_text = ""
    for part in msg.walk():
        if part.get_content_type() == "text/html":
            payload = part.get_payload(decode=True) or b""
            html_text += payload.decode("utf-8", errors="replace")
    if not html_text:
        html_text = data.decode("utf-8", errors="replace")
    text = re.sub(r"<(style|script).*?</\1>", " ", html_text, flags=re.DOTALL | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = _html.unescape(text)
    return re.sub(r"[ \t]{2,}", " ", re.sub(r"\n\s*\n\s*\n+", "\n\n", text)).strip()
