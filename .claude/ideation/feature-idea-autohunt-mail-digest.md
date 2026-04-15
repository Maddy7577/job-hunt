# Feature Idea: AutoHunt Gmail Digest

## Name
**AutoHunt Gmail Digest** *(per-job email with tailored resume attachment)*

## One-line Summary
For every job displayed in the AutoHunt results table, send a personalised Gmail containing the job details and apply link, plus an ATS-optimised version of the primary resume tailored to that specific job description — attached as a PDF.

---

## What It Does

After an AutoHunt run completes (or on demand via a "Send Digest" button), the app iterates over all job rows in the AutoHunt results table. For each job it:

1. **Tailors the resume (ATS expert mode)** — passes the user's primary resume text and the full job description to **Google Gemini 1.5 Flash** (free tier) with a structured ATS-screener prompt. Gemini analyses the JD as a senior ATS specialist would and produces a role-specific resume that:

   - **Extracts and maps JD requirements** — identifies must-have skills, preferred qualifications, seniority signals, and keyword phrases the ATS will scan for.
   - **Rewrites the professional summary** — crafts a 3–4 sentence opening that mirrors the role's title, core competency language, and seniority level verbatim where accurate.
   - **Re-ranks and rewrites experience bullets** — promotes the most relevant past achievements to the top of each role; rephrases bullets using the JD's exact action verbs and domain terminology (e.g. if the JD says "Worksoft Certify automation suite", the bullet uses that phrase, not just "test automation").
   - **Keyword injection without fabrication** — adds missing JD keywords only where they truthfully apply to existing experience; never invents tools, titles, or metrics not present in the original resume.
   - **Skills section reorder** — moves skills that appear in the JD to the top of the skills list; removes or demotes skills not relevant to this role.
   - **ATS formatting rules** — strips tables, columns, graphics, and special characters that confuse ATS parsers; uses plain section headers (`Experience`, `Skills`, `Education`) that ATS systems reliably parse.
   - **Output contract** — returns the tailored resume as structured plain text with clear section delimiters so the PDF renderer can lay it out consistently.

2. **Generates a PDF** — renders the tailored resume as a clean PDF using **fpdf2** (free, local).

3. **Sends a Gmail** — delivers one email per job via **Gmail SMTP** (free, app-password auth) containing:
   - Job title, company, portal, location, experience level
   - Fit score badge
   - A short excerpt of the job description (first ~300 chars)
   - "Apply →" link
   - Tailored resume PDF as an attachment named `Resume_<Company>_<Role>.pdf`

### Trigger Options
- **Manual**: "Send Digest" button in the AutoHunt tab — sends emails for all jobs currently visible in the table (respecting current filter/sort state).
- *(Future)* Automatic send at end of hunt run.

### Rate-limit Awareness
Gemini 1.5 Flash free tier: 15 RPM, 1500 RPD. For a typical AutoHunt run (50–100 jobs), the app will batch Gemini calls with a small inter-request delay (~4 s) to stay within 15 RPM. Progress shown in a status bar.

---

## Tech Stack (all free)

| Concern | Library / Service | Cost |
|---|---|---|
| Email delivery | Gmail SMTP (`smtplib` + `email` stdlib) | Free |
| LLM resume tailoring | Google Gemini 1.5 Flash API (free tier) | Free |
| PDF generation | `fpdf2` | Free / OSS |
| Resume source text | Existing `resume.raw_text` from DB | — |
| Job data | Existing `Job` rows from AutoHunt search | — |

New env vars required:
```
GMAIL_ADDRESS=you@gmail.com
GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx   # Google app password (not your main password)
GEMINI_API_KEY=AIza...                   # Google AI Studio — free
NOTIFY_EMAIL=you@gmail.com               # recipient (defaults to GMAIL_ADDRESS)
```

---

## UI Changes

### AutoHunt Tab — additions only
- **"Send Digest" button** next to the Hunt button: disabled until a hunt has results; shows a spinner + progress text while sending (`Sending 3 / 47…`).
- **Email settings row** (collapsible, below the Hunt controls): shows `GMAIL_ADDRESS` and `NOTIFY_EMAIL` as read-only labels (configured via `.env`); link to docs on setting up a Gmail app password.

---

## Backend Changes

### New service: `app/services/digest_service.py`
- `tailor_resume(resume_text, job_description) -> str` — calls Gemini API, returns tailored resume as plain text.
- `build_pdf(tailored_text, filename) -> bytes` — renders PDF via fpdf2, returns bytes.
- `send_job_email(job, pdf_bytes, pdf_filename)` — composes and sends one email via Gmail SMTP with PDF attachment.
- `send_digest(search_id, app_context)` — orchestrates the full loop: fetch jobs → tailor → PDF → send, with rate-limit delay.

### New route: `POST /api/autohunt/<search_id>/digest`
- Kicks off `send_digest` in a background thread.
- Returns `{ "status": "started", "total": N }`.
- SSE progress stream: `GET /api/autohunt/<search_id>/digest/stream` — emits `{ "sent": N, "total": M, "current_company": "…" }`.

---

## Out of Scope for This Feature
- Scheduled / automatic daily digest (cron follow-up).
- Editing the resume tailoring prompt from the UI.
- Sending batched / digest-style single emails (one email per job is the intended behaviour).

---

*Feature idea version: 1.0 — 2026-04-14*
