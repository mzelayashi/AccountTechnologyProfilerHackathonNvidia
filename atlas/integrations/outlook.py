"""Open a pre-populated, editable Outlook draft (desktop) via COM, with a mailto: fallback."""
from __future__ import annotations

import urllib.parse
import webbrowser


def draft(to: str, subject: str, body: str, attachment=None) -> dict:
    """Open an editable Outlook compose window (To/Subject/Body pre-filled, file attached).
    Returns {ok, via, error}. Falls back to a mailto: link if Outlook COM isn't available."""
    try:
        import pythoncom  # noqa: F401  (ensures COM is initialized on this thread)
        import win32com.client

        pythoncom.CoInitialize()
        outlook = win32com.client.Dispatch("Outlook.Application")
        mail = outlook.CreateItem(0)  # 0 = olMailItem
        mail.To = to or ""
        mail.Subject = subject or ""
        mail.Body = body or ""
        if attachment:
            try:
                mail.Attachments.Add(str(attachment))
            except Exception:
                pass
        mail.Display(False)  # editable, non-modal — user reviews and sends
        return {"ok": True, "via": "outlook"}
    except Exception as e:  # noqa: BLE001
        # Fallback: mailto (no attachment, body truncated to a safe length).
        try:
            q = urllib.parse.urlencode({"subject": subject or "", "body": (body or "")[:1500]})
            webbrowser.open(f"mailto:{to or ''}?{q}")
            return {"ok": True, "via": "mailto", "error": str(e)}
        except Exception as e2:  # noqa: BLE001
            return {"ok": False, "via": "none", "error": f"{e}; {e2}"}
