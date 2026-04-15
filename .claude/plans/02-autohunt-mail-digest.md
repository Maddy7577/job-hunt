# Plan: AutoHunt Mail Digest (Step 02)

## Context
AutoHunt finds jobs and displays them in a table. This feature closes the loop: after a hunt, the user clicks **Send Digest** and receives one Gmail per job with the job details, apply link, and a role-tailored PDF resume attached. Resume tailoring is done by Gemini 1.5 Flash (free tier) acting as a senior ATS screener. All tech is free: Gmail SMTP, Gemini free API, fpdf2 OSS library.

Spec: `.claude/specs/02-autohunt-mail-digest.md`

**Status: Implemented ✓**

---

## Implementation Order (as executed)

### Step 1 — DB: Add `JobDigestStatus` model
**File:** `app/models.py`

Replaced the initial `digest_sent` integer column design with a proper tracking table:

```python
class JobDigestStatus(db.Model):
    __tablename__ = "job_digest_status"

    job_id      = db.Column(db.Integer, db.ForeignKey("job.id"), primary_key=True)
    status      = db.Column(db.Text, nullable=False, default="New")  # "New" | "Notified"
    notified_at = db.Column(db.DateTime, nullable=True)
```

- `job_id` — FK to `job.id`; identifies the open role being tracked
- `status` — `"New"` on creation → `"Notified"` once email is dispatched
- `notified_at` — UTC timestamp of dispatch

DB reset required: `flask shell` → `db.drop_all(); db.create_all()`

---

### Step 2 — New Service: `app/services/digest_service.py`

Pure Python, no Flask imports at module level.

**Functions:**

| Function | Purpose |
|---|---|
| `tailor_resume(resume_text, jd) -> str` | Calls Gemini 1.5 Flash with 10-rule ATS system prompt; returns plain text resume |
| `build_pdf(tailored_text) -> bytes` | Renders ALLCAPS-delimited resume as single-column A4 PDF via fpdf2 |
| `_sanitise_filename(s) -> str` | Strips non-`[a-zA-Z0-9 _-]` chars from attachment filenames |
| `send_job_email(job, pdf_bytes, filename)` | Builds MIMEMultipart email with HTML body + PDF attachment; sends via Gmail SMTP SSL port 465 |
| `send_digest(search_id, app_ctx, push_fn)` | Orchestrates loop; queries `JobDigestStatus` to skip already-`"Notified"` jobs; sleeps 4 s between Gemini calls |

**Rate-limit guard:** 4 s sleep between each Gemini call (free tier: 15 RPM).

**Idempotency:** queries `JobDigestStatus.query.filter_by(status="Notified")` to collect already-sent job IDs and excludes them via `Job.id.notin_(...)`.

---

### Step 3 — Routes: Extended `app/routes/autohunt.py`

Added module-level digest SSE queue state (mirrors `search.py` pattern):
```python
_digest_queues: dict[int, _queue.Queue] = {}
_digest_lock   = threading.Lock()
_digest_get_queue(search_id) -> Queue
_digest_push(search_id, event, data)
```

**New routes:**

| Method | Path | Behaviour |
|---|---|---|
| `POST` | `/api/autohunt/<id>/digest` | Guards env vars (503 if missing); counts unnotified jobs; starts `_run_digest` thread; returns `{status, total}` |
| `GET` | `/api/autohunt/<id>/digest/stream` | SSE stream; 30 s timeout ping; breaks on `__digest_done__` |
| `GET` | `/api/autohunt/email-config` | Returns `{gmail_address, notify_email, configured}`; never exposes app password |

---

### Step 4 — HTML: `app/static/index.html`

Hunt button wrapped in flex div; Send Digest button added alongside it; digest progress bar and collapsible email config `<details>` block added below.

---

### Step 5 — JavaScript: `app/static/app.js`

| Addition | Purpose |
|---|---|
| `ahState.digestTotal` | Tracks total jobs in active digest run |
| `ahLoadEmailConfig()` | Fetches `/email-config` on tab load; shows warning if unconfigured |
| `ahSendDigest()` | POST → open SSE stream; handles `nothing_to_send` gracefully |
| `ahOpenDigestStream(id)` | Consumes `digest_progress`, `digest_done`, `error` SSE events; updates progress bar + toast |
| Tab activation | Calls both `ahLoadProfile()` and `ahLoadEmailConfig()` on AutoHunt tab open |
| Hunt complete hook | Enables `#ahDigestBtn` when `d.status === "done" && d.total > 0` |

---

### Step 6 — Config files

- `requirements.txt`: `fpdf2>=2.7`, `google-generativeai>=0.7`
- `.env.example`: `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, `GEMINI_API_KEY`, `NOTIFY_EMAIL`

---

## Reused Patterns
- SSE queue/push: mirrors `search.py:13–27`
- SSE stream generator (30 s ping, sentinel break): mirrors `search.py:146–171`
- `showToast(msg, type)`: `app.js:27–34`
- `escHtml(str)`: `app.js:711–718`
- Button disable/re-enable: same pattern as `ahHuntBtn`
- Service convention: pure Python, no Flask context at module level (`autohunt_filter.py`)

---

## Verification Checklist
1. Reset DB: `flask shell` → `db.drop_all(); db.create_all()`
2. `pip install fpdf2 google-generativeai`
3. Set `GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`, `GEMINI_API_KEY`, `NOTIFY_EMAIL` in `.env`
4. `python run.py`
5. Upload resume → run AutoHunt hunt → results table loads
6. Click **Send Digest** → progress bar fills 0→100%
7. Check inbox: one email per job, each with PDF attachment
8. Open a PDF: single-column, ALLCAPS headers, no tables/images
9. Click **Send Digest** again → "All jobs already sent" toast (idempotency)
10. `job_digest_status` rows show `status = "Notified"` and populated `notified_at`
11. Remove `GEMINI_API_KEY` from `.env` → POST returns HTTP 503
12. `APIFY_MOCK=true` hunt flow unaffected
