"""Live web research for the Brainwave research agent.

No API key, no new dependencies — scrapes DuckDuckGo (lite, then html as fallback) with httpx and
extracts page text with lxml (both already vendored in the venv). Everything is best-effort: any
failure (blocked egress, markup drift) returns empty so the Brainwave degrades gracefully to the
model's own knowledge instead of crashing.
"""
from __future__ import annotations

import html as _html
import re

import httpx

_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
       "Chrome/120.0 Safari/537.36")
_HDRS = {"User-Agent": _UA, "Accept-Language": "en-US,en;q=0.9"}
_TIMEOUT = 12.0

# DuckDuckGo result anchors look like  <a ... class="result__a" href="URL">TITLE</a>
# (html endpoint) and  <a ... class="result-link" href="URL">TITLE</a>  (lite endpoint),
# each followed by a snippet block. We parse defensively with regex (no bs4 in the venv).
_LINK_HTML = re.compile(r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S)
_SNIP_HTML = re.compile(r'class="result__snippet"[^>]*>(.*?)</a>', re.S)
_ROW_LITE = re.compile(r'<a[^>]*class="result-link"[^>]*href="([^"]+)"[^>]*>(.*?)</a>'
                       r'.*?class="result-snippet"[^>]*>(.*?)</td>', re.S)


def _detag(s: str) -> str:
    return _html.unescape(re.sub(r"<.*?>", "", s or "")).strip()


def _unwrap_ddg(url: str) -> str:
    """DDG often wraps links as //duckduckgo.com/l/?uddg=<encoded>. Pull the real target out."""
    m = re.search(r"[?&]uddg=([^&]+)", url or "")
    if m:
        from urllib.parse import unquote
        return unquote(m.group(1))
    if url.startswith("//"):
        return "https:" + url
    return url


def _blocked_domains() -> list[str]:
    """Domains the research agent must skip (Guardrails lever). Lowercased, 'www.' stripped."""
    try:
        from atlas.store import settings
        import re
        raw = settings.load().get("guardrails_blocked_domains", "") or ""
        return [d.strip().lower().lstrip("www.") for d in re.split(r"[,\n;]+", raw) if d.strip()]
    except Exception:  # noqa: BLE001
        return []


def _is_blocked(url: str, blocked: list[str]) -> bool:
    if not blocked:
        return False
    try:
        from urllib.parse import urlparse
        host = (urlparse(url).hostname or "").lower()
        if host.startswith("www."):
            host = host[4:]
        return any(host == d or host.endswith("." + d) for d in blocked)
    except Exception:  # noqa: BLE001
        return False


def search(query: str, k: int = 8) -> list[dict]:
    """Return up to k web results as {title, url, snippet}. Empty list on any failure.
    Results from Guardrails-blocked domains are dropped."""
    q = (query or "").strip()
    if not q:
        return []
    blocked = _blocked_domains()
    for url, parser in (("https://html.duckduckgo.com/html/", "html"),
                        ("https://lite.duckduckgo.com/lite/", "lite")):
        try:
            r = httpx.post(url, data={"q": q}, headers=_HDRS, timeout=_TIMEOUT,
                           follow_redirects=True)
            if r.status_code != 200 or not r.text:
                continue
            out: list[dict] = []
            if parser == "html":
                links = _LINK_HTML.findall(r.text)
                snips = _SNIP_HTML.findall(r.text)
                for i, (href, title) in enumerate(links[:k]):
                    out.append({"title": _detag(title), "url": _unwrap_ddg(href),
                                "snippet": _detag(snips[i]) if i < len(snips) else ""})
            else:
                for href, title, snip in _ROW_LITE.findall(r.text)[:k]:
                    out.append({"title": _detag(title), "url": _unwrap_ddg(href),
                                "snippet": _detag(snip)})
            out = [o for o in out if o["title"] and o["url"].startswith("http")
                   and not _is_blocked(o["url"], blocked)]
            if out:
                return out
        except Exception:  # noqa: BLE001 — best-effort
            continue
    return []


def fetch(url: str, cap: int = 4000) -> str:
    """Fetch a page and return its readable text (capped). Empty on failure."""
    try:
        r = httpx.get(url, headers=_HDRS, timeout=_TIMEOUT, follow_redirects=True)
        if r.status_code != 200 or not r.text:
            return ""
        from lxml import html as lxhtml
        doc = lxhtml.fromstring(r.text)
        for bad in doc.xpath("//script | //style | //nav | //footer | //header | //noscript"):
            bad.getparent().remove(bad)
        text = doc.text_content()
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n\s*\n+", "\n", text).strip()
        return text[:cap]
    except Exception:  # noqa: BLE001
        return ""


def research_brief(query: str, on_log=None, k: int = 6, deep: int = 2) -> str:
    """Search the web and return a compact SOURCES block for grounding the research agent.
    Fetches the top `deep` pages for depth; the rest contribute title + snippet. Returns "" if the
    web is unreachable (caller then falls back to model knowledge)."""
    blocked = _blocked_domains()
    if blocked and on_log:
        on_log(f"🛡️ Guardrails: skipping research sources from {', '.join(blocked)}.")
    results = search(query, k=k)
    if not results:
        if on_log:
            on_log("🌐 web search unavailable — falling back to model knowledge.")
        return ""
    if on_log:
        on_log(f"🌐 web search: {len(results)} source(s) for “{query}”.")
    blocks = []
    for i, r in enumerate(results, 1):
        body = r.get("snippet", "")
        if i <= deep:
            page = fetch(r["url"])
            if page:
                body = page
        blocks.append(f"[{i}] {r['title']} — {r['url']}\n{body}".strip())
    return "\n\n".join(blocks)
