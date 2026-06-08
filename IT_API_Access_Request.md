# Technical request — Graph/Copilot API access to replace the browser-automation workaround for the "ATLAS" SA tooling

> **How to use this document:** This is a ready-to-send email to the IT / Identity team. Before sending,
> fill the two bracketed placeholders in §4 — the app registration's **Application (Client) ID** and the
> **tenant ID**. Do **not** paste any client secret into this file or the email; the secret lives only in
> the local `.env`.

---

**To:** [IT / Identity team]
**From:** Manuel Zelaya — Solutions Architect, SHI
**Subject:** Technical request — Graph/Copilot API access to replace browser-automation workaround for the "ATLAS" SA tooling

Hi [IT / Identity team],

I'm building an internal Solutions-Architect productivity tool ("ATLAS") that today drives the Microsoft 365 Copilot **web app** through browser automation under my own interactive sign-in. That works, but it's a brittle stopgap. I'd like to move it onto **supported Microsoft APIs** at the same capability level. Below is (1) exactly what I hit when I first tried the API route, (2) why the current browser approach is a workaround we should retire, and (3) a capability-by-capability mapping to the real Microsoft APIs, with the specific permission scopes, admin-consent requirements, and licensing each one needs. I've tried to be precise about which scopes are *admin-restricted* so you can scope this to least privilege.

---

## 1. What I ran into on the initial API attempt

I registered a single-tenant application in Entra ID and attempted to call Microsoft Graph. I was blocked at several points, all of which are by-design tenant governance — not bugs:

- **Admin-restricted permission scopes.** The permissions this project needs (meeting transcripts, tenant content retrieval, the Copilot APIs, application-level mail/calendar) are classified by Microsoft as **admin-restricted**. A non-admin can *select* them on the app registration, but the app cannot function until a **Global Administrator / Privileged Role Administrator / Cloud Application Administrator grants admin consent** on the Enterprise Application. The `/adminconsent` flow returns `AADSTS90094` (admin consent required) for me.
- **User consent appears to be disabled tenant-wide.** Even normally user-consentable delegated scopes (e.g. `Calendars.Read`) failed for me, which indicates the tenant has **"User consent for applications" set to "Do not allow"** (Entra → Enterprise applications → Consent and permissions). So *every* scope this app needs — even the low-risk ones — requires an admin action.
- **Application-only access to Teams meeting data is gated by a Teams policy, not just consent.** App-only (unattended) reads of online-meeting transcripts/recordings additionally require a Teams admin to create and assign an **application access policy** (`New-CsApplicationAccessPolicy` + `Grant-CsApplicationAccessPolicy`) scoping the app to specific users. Consent alone is insufficient.
- **Copilot API licensing.** The Microsoft 365 **Copilot API family** (Retrieval API, interaction export, AI meeting insights) requires the tenant/identity context to be covered by **Microsoft 365 Copilot licensing**. I already hold a Copilot license (I use the web app daily), but the service/app context needs to be permitted to use it.

Net: the blocker is **admin consent + a Teams application access policy + confirmation of Copilot API licensing**, not a technical impossibility. That's the core of my ask.

---

## 2. Why the current browser approach should be retired

To keep moving, ATLAS currently automates the Copilot **web UI** (Selenium-driven Edge/Chrome) under my own delegated, interactive session. Functionally it reproduces what I'd do by hand, but as a production posture it's poor and I'd rather not run it long-term:

- **No app-only / unattended auth** — it depends on a live, interactively signed-in browser profile sitting on my workstation (a stored, authenticated session). That's a worse security footprint than a properly-scoped, admin-governed app registration.
- **Brittle** — any Copilot UI change breaks scraping; there's no contract/versioning like Graph has.
- **Not auditable or least-privilege** — it inherits *all* of my delegated access via the UI, rather than a reviewed, narrow set of scopes you can see and revoke in the Enterprise App.
- **Not governable** — you can't apply Conditional Access app controls, RBAC-for-Applications scoping, or application access policies to a screen-scraper the way you can to a Graph app.

Moving to Graph/Copilot APIs *improves* our security and governance posture — it replaces an opaque interactive session with an explicit, admin-consented, least-privilege app you control.

---

## 3. Capability-by-capability mapping to real Microsoft APIs

For each thing ATLAS does today via the UI, here is the supported Microsoft API, the host/endpoint, the delegated and application scopes, and the admin/licensing requirement. (Where a surface is currently `beta`, I've said so — exact paths should be confirmed against current Microsoft Learn docs at implementation time.)

### 3.1 Read the day's meetings (the dashboard / "meetings that occurred that day")
- **API:** Microsoft Graph **Calendar** — `GET /me/calendarView?startDateTime=…&endDateTime=…` (or `/users/{id}/calendarView` app-only). Returns subject, organizer, attendees, start/end, and the Teams `onlineMeeting.joinUrl`.
- **Scopes:** delegated `Calendars.Read`; application `Calendars.Read`.
- **Admin:** delegated is normally user-consentable but **needs admin here because tenant user-consent is disabled**; application **requires admin consent** and can/should be scoped to just my mailbox via **RBAC for Applications** (`Application` RBAC, Exchange) so the app can't read the whole tenant's calendars.

### 3.2 Pull meeting transcripts (the core input to trip reports — today scraped)
- **API:** Microsoft Graph **online meeting transcripts** —
  - resolve the meeting: `GET /me/onlineMeetings?$filter=JoinWebUrl eq '{url}'`
  - list: `GET /me/onlineMeetings/{meetingId}/transcripts`
  - fetch content (VTT/text): `GET /me/onlineMeetings/{meetingId}/transcripts/{transcriptId}/content?$format=text/vtt`
  - (app-only variants under `/users/{userId}/onlineMeetings/…`)
  - For automatic capture, subscribe to change notifications: `/communications/onlineMeetings/getAllTranscripts`.
- **Scopes:** delegated `OnlineMeetingTranscript.Read.All`, plus `OnlineMeetings.Read` to enumerate meetings; application `OnlineMeetingTranscript.Read.All`.
- **Admin:** **admin consent required (both delegated and application)**. App-only **also requires a Teams application access policy** (`New-CsApplicationAccessPolicy`/`Grant-CsApplicationAccessPolicy`) scoping the app to my user.
- **Recording analog (optional):** `OnlineMeetingRecording.Read.All` via `/onlineMeetings/{id}/recordings`.

### 3.3 Copilot's AI meeting recap / notes / action items
- **API:** Microsoft Graph **AI insights for meetings** (`aiInsights` under an online meeting) — `GET /me/onlineMeetings/{id}/aiInsights` (and `/users/{id}/onlineMeetings/{id}/aiInsights`). Returns Copilot-generated meeting notes, action items, and mention events. **This is `beta`.**
- **Scopes:** delegated `OnlineMeetingAiInsight.Read.All` (or `.Read.Chat`); application equivalent.
- **Admin / licensing:** **admin consent**, **Microsoft 365 Copilot license required**, and (app-only) the same Teams application access policy as 3.2.
- **Note:** if this beta API is not acceptable for production, the fallback is to take the **transcript from 3.2** and generate the recap ourselves (see 3.5) — that's actually how ATLAS produces trip reports today.

### 3.4 Read filed/customer content in SharePoint/OneDrive (if/when artifacts live in M365)
- **API:** Microsoft Graph **Files/Sites/Search** — `GET /me/drive/…`, `GET /sites/{id}/drive/…`, `POST /search/query`.
- **Scopes:** delegated/application `Files.Read.All`, `Sites.Read.All` (read-only is sufficient).
- **Admin:** **admin consent required** for the `.All` scopes; app-only can be scoped to specific sites via **`Sites.Selected`** for least privilege.

### 3.5 "Ask ATLAS" — grounded Q&A over tenant data (what Copilot **Work** mode does today)
This is the one place where Microsoft **does not** expose a single public REST endpoint that returns the same grounded, generated answer the Copilot web app gives. I want to be completely straight about that. There are **two supported ways** to reproduce it, and I'm flexible on which you prefer:

- **Option A — Retrieval API + our own model (the "build what Copilot does internally" path):**
  - **Microsoft 365 Copilot Retrieval API** — `POST https://graph.microsoft.com/beta/copilot/retrieval` (Copilot API family; recently GA-ing, confirm current version). Returns the most relevant text chunks from the **same Microsoft Graph semantic index Copilot uses** (SharePoint/OneDrive, and Microsoft 365 Copilot connectors), with citations.
  - **Scopes:** `Files.Read.All` + `Sites.Read.All` (delegated or application); **Microsoft 365 Copilot license required**; **admin consent required**.
  - Then synthesize the answer with **Azure OpenAI** (`POST {azure-openai-endpoint}/openai/deployments/{deployment}/chat/completions`) in our own subscription. This gives us Copilot-grade grounding with full control and auditability.
- **Option B — Copilot Studio agent + Direct Line:** build a **Copilot Studio** agent grounded in the relevant tenant knowledge, publish it, and converse with it programmatically via the **Direct Line API** (or the **Microsoft 365 Agents SDK**). This is the closest to "a Copilot you can call as a service."

Either is supported and governable. **There is no `POST /copilot/chat {prompt}` general-purpose endpoint** that mirrors the web UI's Work answers for arbitrary delegated use — so I'd build on A or B rather than wait for one.

### 3.6 Web-research mode (what Copilot **Web** mode does today)
- This uses no tenant data, so it doesn't need Graph at all. The supported replacement is **Azure OpenAI** in our subscription, optionally with **Grounding with Bing Search (Azure AI Foundry / Azure AI Agent Service)** for fresh web facts. This is the easiest piece to move off the browser.

### 3.7 Email the trip report / open an Outlook draft (the "Email" button)
- **API:** Microsoft Graph **Mail** — `POST /me/sendMail`, or create a draft with `POST /me/messages`.
- **Scopes:** delegated `Mail.Send` (and `Mail.ReadWrite` for drafts); application `Mail.Send`.
- **Admin:** delegated normally user-consentable (blocked here by disabled user consent → needs admin); application `Mail.Send` **requires admin consent** and should be scoped to my mailbox via **RBAC for Applications** so the app can't send as anyone else.

### 3.8 Attendee/people enrichment (titles, company — used in briefings)
- **API:** Microsoft Graph **Users/People** — `GET /users/{id}`, `GET /me/people`.
- **Scopes:** `User.Read.All`, `People.Read.All`. **Admin consent required.**

### 3.9 (Optional, governance) Audit of Copilot interactions
- **API:** **Microsoft 365 Copilot Interaction Export API** — `GET /copilot/users/{userId}/interactionHistory/getAllEnterpriseInteractions` (`beta`). For compliance/export, not for generating answers.
- **Scope:** `AiEnterpriseInteraction.Read.All`; **admin consent**, **Copilot license**. Not required for core function — listed for completeness in case you want oversight of what the tool asks.

---

## 4. The concrete ask (least-privilege, ordered by what unblocks the most)

For the **delegated-only** version (runs under my sign-in — smallest change, gets us off the browser immediately), I need admin consent on app **[Application/Client ID: __________]**, tenant **[Tenant ID: __________]**, for:

1. `Calendars.Read`
2. `OnlineMeetings.Read`
3. `OnlineMeetingTranscript.Read.All`
4. `Files.Read.All`, `Sites.Read.All` (for the Retrieval API + document reads)
5. `Mail.Send` (and `Mail.ReadWrite` if you'd prefer drafts over direct send)
6. `User.Read.All`, `People.Read.All`
7. *(beta, optional)* `OnlineMeetingAiInsight.Read.All`

Plus:

8. **Confirm Microsoft 365 Copilot licensing** permits the Copilot **Retrieval API** (and AI insights) for my account/app context.
9. **Re-enable user consent** for this app specifically, *or* simply grant admin consent above (admin consent makes the user-consent setting moot for this app).

If you'd rather it run **unattended/app-only** (service identity, no interactive session at all — my preferred end state), additionally:

10. Admin consent for the **application** versions of the scopes above, **scoped to least privilege**: **RBAC for Applications** to limit Mail/Calendar to my mailbox, **`Sites.Selected`** to limit file access to designated sites, and a **Teams application access policy** (`New-CsApplicationAccessPolicy`/`Grant-CsApplicationAccessPolicy`) limiting online-meeting/transcript access to my user only.
11. (If we go the Azure OpenAI route for 3.5/3.6) approval to stand up an **Azure OpenAI** resource in our subscription.

I'm happy to apply **Conditional Access app controls**, certificate-based credentials (no client secrets), and IP/device restrictions on this app — whatever standards you want. The whole point is to replace the current opaque interactive browser session with an explicit, narrowly-scoped, fully-auditable app you own and can revoke.

Happy to walk through any of this live, or to start with just the delegated set (#1–9) as a first phase and evaluate app-only afterward.

Thanks,
Manuel Zelaya
Solutions Architect, SHI

---

## Appendix — scope summary

| # | Capability | Primary API / endpoint | Delegated scope | Application scope | Admin consent | Extra requirement |
|---|------------|------------------------|-----------------|-------------------|---------------|-------------------|
| 3.1 | Day's meetings / calendar | Graph `GET /me/calendarView` | `Calendars.Read` | `Calendars.Read` | Yes (user consent disabled) | App-only: RBAC for Applications to scope to my mailbox |
| 3.2 | Meeting transcripts | Graph `GET /onlineMeetings/{id}/transcripts/{tid}/content` | `OnlineMeetingTranscript.Read.All` + `OnlineMeetings.Read` | `OnlineMeetingTranscript.Read.All` | Yes | App-only: Teams application access policy |
| 3.3 | Copilot meeting recap/notes (`beta`) | Graph `GET /onlineMeetings/{id}/aiInsights` | `OnlineMeetingAiInsight.Read.All` | same | Yes | M365 Copilot license + Teams app access policy |
| 3.4 | SharePoint/OneDrive content | Graph Files/Sites/`POST /search/query` | `Files.Read.All`, `Sites.Read.All` | same (or `Sites.Selected`) | Yes | — |
| 3.5 | Grounded tenant Q&A | **Copilot Retrieval API** `POST /beta/copilot/retrieval` + Azure OpenAI **or** Copilot Studio + Direct Line | `Files.Read.All`, `Sites.Read.All` | same | Yes | M365 Copilot license; **no 1:1 chat endpoint exists** |
| 3.6 | Web research | Azure OpenAI (+ Bing grounding) | n/a (own subscription) | n/a | n/a | Azure OpenAI resource |
| 3.7 | Send / draft email | Graph `POST /me/sendMail` or `/me/messages` | `Mail.Send` (`Mail.ReadWrite` for drafts) | `Mail.Send` | Yes (app) | App-only: RBAC for Applications |
| 3.8 | People enrichment | Graph `GET /users/{id}`, `/me/people` | `User.Read.All`, `People.Read.All` | same | Yes | — |
| 3.9 | Copilot interaction audit (`beta`) | **Copilot Interaction Export** `getAllEnterpriseInteractions` | `AiEnterpriseInteraction.Read.All` | same | Yes | M365 Copilot license |

**Reality-check notes (no invented APIs):**
- There is **no** public "return the rendered Copilot Work answer" endpoint and **no** "Copilot web search" scope — those map to the **Retrieval API + our own model** (§3.5) and **Azure OpenAI + Bing grounding** (§3.6) respectively.
- `aiInsights` (§3.3) and the **Retrieval API** (§3.5) version status (`beta` vs `v1.0`) should be confirmed against current Microsoft Learn docs at build time; Microsoft moved several of these through 2025.
