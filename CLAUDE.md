# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Job Hunt is a Flask web application that fans out job searches across 17 portals via Apify actors, scores results against an uploaded resume, and presents a ranked table. See the full spec at `.claude/specs/job-hunt-app-spec.md`.

## Running the app

```bash
# Install dependencies
pip install -r requirements.txt

# Start the dev server
python run.py
```

The app is served at `http://localhost:5100`.

## Environment

Copy `.env.example` to `.env`. For local development no API keys are needed:

```
APIFY_MOCK=true          # uses fake job data — no Apify credits consumed
FLASK_SECRET_KEY=any-string
```

When ready to enable real job scraping, set `APIFY_MOCK=false` and add:
```
APIFY_API_TOKEN=apify_api_xxxxxxxxxxxx
```

When ready to enable Claude-based scoring (paid), add:
```
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxx
```

When ready to enable the AutoHunt Gmail Digest (free), add:
```
GMAIL_ADDRESS=you@gmail.com
GMAIL_APP_PASSWORD=xxxx-xxxx-xxxx-xxxx   # Google App Password (myaccount.google.com/apppasswords)
GEMINI_API_KEY=AIza...                   # Google AI Studio free tier (aistudio.google.com)
NOTIFY_EMAIL=you@gmail.com               # Recipient (defaults to GMAIL_ADDRESS if unset)
```

## Architecture

```
app/
  __init__.py          # Flask app factory; registers blueprints, DB, CORS
  models.py            # SQLAlchemy models: Resume, Search, Job, AutoHuntProfile, JobDigestStatus
  routes/
    resume.py          # /api/resume  — upload, metadata, download
    search.py          # /api/search  — start search, SSE progress stream, results
    jobs.py            # /api/jobs, /api/saved, /api/history
    autohunt.py        # /api/autohunt — profile, hunt, digest, email-config
  services/
    apify_service.py   # Mock mode (default) + real Apify actors (commented out)
    scorer.py          # TF-IDF (instant) + sentence-transformers semantic score (async, free)
    resume_parser.py   # Extracts plain text from PDF (pdfminer) or DOCX (python-docx)
    autohunt_filter.py # Language + visa/residency post-fetch filters for AutoHunt
    digest_service.py  # Gemini ATS resume tailoring + fpdf2 PDF + Gmail SMTP send
  static/
    index.html / app.js / style.css   # Single-page UI
config/
  portals.json         # Actor slug + param_map per portal — edit here to add/remove portals
uploads/               # Original resume files written at upload time
```

### Key design points

**Mock mode (current default):** `apify_service.py` has `MOCK_MODE = True` (controlled by `APIFY_MOCK` env var). In mock mode, `run_actor()` calls `_mock_run_actor()` which returns realistic fake job listings without hitting the Apify API. The real Apify call is preserved in a commented-out block directly below. To switch to real scraping: set `APIFY_MOCK=false` in `.env` and uncomment the Apify block.

**Portal configuration is data, not code.** `config/portals.json` holds each portal's Apify actor ID and a `param_map` that translates the app's canonical parameter values (e.g. `experience: "senior"`) into the vocabulary each portal expects. Adding a new portal means adding a JSON entry — no Python changes required.

**Search lifecycle:** `POST /api/search` persists the search record (status `pending`), then hands off to a `ThreadPoolExecutor` (one thread per portal). Each thread calls the actor (mock or real), normalises results, deduplicates by `hash(company+title+location)`, and inserts `Job` rows. Status updates are pushed to the client via SSE on `GET /api/search/<id>/stream`.

**Two-phase scoring:**
1. TF-IDF cosine similarity runs synchronously on each `Job` row as it arrives → instant `fit_score`.
2. A background thread runs `sentence-transformers` (`all-MiniLM-L6-v2`, free, local) → overwrites `fit_score` with a semantic score and populates `fit_rationale` with a keyword-based one-sentence explanation. The frontend polls `/api/jobs/<id>/score` and refreshes the badge in-place.
3. *(Future)* Claude API scoring is preserved in a commented-out block in `scorer.py`. Uncomment and set `ANTHROPIC_API_KEY` to upgrade to AI rationale.

**Resume storage:** Original binary is stored as a BLOB in `resume.file_data` and also written to `uploads/<timestamp>_<filename>`. `resume.raw_text` holds the extracted plain text used for scoring. All resume versions are kept; the latest is `SELECT … ORDER BY id DESC LIMIT 1`.

**AutoHunt:** A dedicated tab pre-configured for the user's profile (Pune, India; 11+ yrs; open to world). One click fans out a search across all portals. Post-fetch filters in `autohunt_filter.py` drop non-English-language and no-visa-sponsorship listings before they are saved.

**AutoHunt Gmail Digest:** After a hunt, the **Send Digest** button dispatches one Gmail per job result. `digest_service.py` calls Gemini 1.5 Flash (free tier) to rewrite the user's resume as an ATS-optimised PDF for that specific role, then sends it as an attachment via Gmail SMTP. Notification state is tracked in `JobDigestStatus` (`job_id`, `status`: `"New"` → `"Notified"`, `notified_at`). A job with `status = "Notified"` is never emailed again. Gemini calls are rate-limited to 15 RPM (4 s sleep between calls) to stay within the free tier.

## Database

SQLite, managed via Flask-SQLAlchemy. Schema is in `app/models.py`.

| Table | Purpose |
|---|---|
| `resume` | Uploaded resume files (binary + extracted text) |
| `search` | Each search run (params + status) |
| `job` | Individual job listings linked to a search |
| `autohunt_profile` | Persisted AutoHunt skills list (single row, id=1) |
| `job_digest_status` | Per-job email notification state (`job_id`, `status`, `notified_at`) |

To reset (required after schema changes — SQLite does not auto-add columns):

```bash
flask shell
>>> from app import db; db.drop_all(); db.create_all()
```

## Apify integration (when ready)

Real actor calls are in `app/services/apify_service.py` in a commented-out block inside `run_actor()`. To enable:

1. Set `APIFY_MOCK=false` in `.env`
2. Set `APIFY_API_TOKEN=...` in `.env`
3. Uncomment the Apify block in `run_actor()`
4. Uncomment `apify-client>=1.7` in `requirements.txt` and `pip install -r requirements.txt`

`maxItems` defaults to 50 (configurable per search via the UI slider).

## Feature Development Workflow

New features follow an ideation-first, spec-driven process:

1. **Describe** the feature to Claude Code in plain language.
2. **Claude distills** the requirement into a clear, workable prompt and saves it to `.claude/ideation/feature-idea.md`.
3. **Claude notifies** you: _"feature-idea.md updated with the requirement"_.
4. **Review** the prompt in `feature-idea.md` and adjust if needed.
5. **Run `/feature-create-spec <step> <feature-name>`** — Claude reads `feature-idea.md`, generates a detailed spec saved to `.claude/specs/<step>-<feature-slug>.md`, and archives the idea prompt as `.claude/ideation/feature-idea-<feature-slug>.md`.
6. **Review the spec**, then enter Plan mode (Shift+Tab twice) to begin implementation.

### .claude folder structure

```
.claude/
  specs/       # App specification + per-feature spec files
  commands/    # Custom Claude Code slash commands (.md files)
  ideation/    # feature-idea.md (active) + feature-idea-<slug>.md (archived per feature)
```

`feature-idea.md` is a reusable single file — it is overwritten with each new feature idea. A dated archive copy (`feature-idea-<slug>.md`) is saved automatically by `/feature-create-spec`.
