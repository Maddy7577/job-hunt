# Job Hunt — Application Specification

## Overview

An interactive web application that monitors job opportunities across **all major job portals** via **Apify actors** for comprehensive coverage. The user supplies their search parameters (role, location, experience, etc.) and uploads a resume. On clicking **Find**, the app fans out parallel Apify actor runs, normalises results into a unified schema, scores every listing against the resume, and presents a ranked, sortable table with expandable descriptions and direct apply links.

---

## Goals

1. Cover as many job portals as possible — not limited to the "big three".
2. Let every search parameter (role, location, experience, salary, date, portals, etc.) be user-configurable.
3. Score every listing against the uploaded resume and explain the score.
4. Store the original resume file (PDF / DOCX) alongside extracted text.
5. Present results in a clean table: Company | Role | Experience | Fit Score | JD (Read More) | Apply.

---

## Tech Stack

| Layer | Choice | Reason |
|---|---|---|
| Backend | Python 3 / Flask | Lightweight REST API; already installed |
| Job data | **Apify** (actor-per-portal) — *real calls disabled until ready* | Managed scrapers for every major portal; handles anti-bot, pagination, JS rendering |
| Job data (dev) | **Mock mode** (`APIFY_MOCK=true`) | Returns realistic fake listings; zero cost during development |
| Resume parsing | `pdfminer.six` + `python-docx` | Extract text from PDF / DOCX |
| Fit scoring (fast) | TF-IDF cosine (`scikit-learn`) | Instant score on job arrival |
| Fit scoring (async) | `sentence-transformers` (`all-MiniLM-L6-v2`) + keyword rationale | Free, runs locally; better semantic similarity than TF-IDF |
| Fit scoring (future) | Claude API (`claude-haiku`) — *commented out* | Upgrade path once API key is available; preserved in `scorer.py` |
| Frontend | Bootstrap 5 + vanilla JS | No build step; clean responsive UI |
| Storage | SQLite via Flask-SQLAlchemy | Zero-config; stores file blobs, search params, results |
| Async | `concurrent.futures.ThreadPoolExecutor` | Parallel actor runs |
| Config | `.env` file + `python-dotenv` | All keys / params externalised |

---

## Apify — Portal Coverage

Apify hosts ready-made actors for every major job board. The app will call them in parallel. The list below is the **default set**; it is fully configurable via the portal checkboxes in the UI.

| Portal | Apify Actor (slug) | Notes |
|---|---|---|
| LinkedIn | `curious_coder/linkedin-jobs-search` | Title, company, location, JD, apply URL |
| Indeed | `misceres/indeed-scraper` | Full JD, salary range, remote flag |
| Glassdoor | `bebity/glassdoor-jobs-scraper` | Rating, salary estimate |
| ZipRecruiter | `curious_coder/ziprecruiter-scraper` | US-heavy, broad SMB coverage |
| Monster | `epctex/monster-scraper` | Legacy board; still has exclusive listings |
| SimplyHired | `epctex/simplyhired-scraper` | Aggregator; finds niche postings |
| CareerBuilder | `epctex/careerbuilder-scraper` | Strong enterprise listings |
| Dice | `epctex/dice-scraper` | Tech-focused; deep role metadata |
| Wellfound (AngelList) | `curious_coder/wellfound-scraper` | Startup ecosystem |
| RemoteOK | `epctex/remoteok-scraper` | Remote-only roles |
| We Work Remotely | `epctex/weworkremotely-scraper` | Remote-only roles |
| Greenhouse | `epctex/greenhouse-jobs-scraper` | ATS; many tech companies post exclusively here |
| Lever | `epctex/lever-jobs-scraper` | ATS; startup-heavy |
| Workday | `epctex/workday-jobs-scraper` | Enterprise ATS; Fortune 500 |
| Naukri (India) | `curious_coder/naukri-scraper` | South-Asia market |
| Reed (UK) | `epctex/reed-scraper` | UK market |
| Totaljobs (UK) | `epctex/totaljobs-scraper` | UK market |

> **Adding more portals:** Drop a new actor slug into `config/portals.json` — no code change required.

### Apify Integration Pattern

```python
import os
from apify_client import ApifyClient

client = ApifyClient(os.getenv("APIFY_API_TOKEN"))

def run_actor(actor_id: str, input_payload: dict) -> list[dict]:
    run = client.actor(actor_id).call(run_input=input_payload)
    return list(client.dataset(run["defaultDatasetId"]).iterate_items())
```

Each actor receives a **normalised input payload** built from the search parameters (see Parameterisation section below).

---

## Parameterisation

All search inputs are first-class parameters stored in the database and passed verbatim to Apify actors. No hard-coded values anywhere.

### User-facing parameters

| Parameter | UI control | DB column | Apify input key (common) |
|---|---|---|---|
| `roles` | Tag input (multi-value) | `roles` (JSON array) | `position` / `keywords` |
| `location` | Text + "Remote" toggle | `location` | `location` |
| `remote_only` | Toggle | `remote_only` (bool) | `remote` |
| `experience` | Dropdown | `experience` | `experienceLevel` |
| `date_posted` | Dropdown | `date_posted` | `datePosted` |
| `salary_min` | Number input (optional) | `salary_min` | `salaryMin` |
| `salary_currency` | Dropdown (optional) | `salary_currency` | `salaryCurrency` |
| `country` | Dropdown | `country` | `country` |
| `employment_type` | Multi-checkbox | `employment_type` (JSON) | `employmentType` |
| `portals` | Multi-checkbox | `portals` (JSON array) | — (selects which actors to run) |
| `max_results_per_portal` | Number slider (default 50) | `max_results` | `maxItems` |

### Experience levels (dropdown)

| Display label | Value stored / passed |
|---|---|
| Internship | `internship` |
| Entry Level (0–2 yrs) | `entry` |
| Mid Level (2–5 yrs) | `mid` |
| Senior (5–8 yrs) | `senior` |
| Lead / Principal (8+ yrs) | `lead` |
| Executive / C-Suite | `executive` |

> **Why parameterise experience?** Each actor maps `experienceLevel` to its own portal vocabulary (e.g., LinkedIn's `2`, Indeed's `entry_level`). A central `portal_param_map` dict in `config/portals.json` handles the translation so the rest of the code stays clean.

### `config/portals.json` structure

```json
{
  "linkedin": {
    "actor_id": "curious_coder/linkedin-jobs-search",
    "enabled": true,
    "param_map": {
      "experience": {
        "internship": "1",
        "entry": "2",
        "mid": "3",
        "senior": "4",
        "lead": "5",
        "executive": "6"
      },
      "date_posted": {
        "any": "",
        "day": "r86400",
        "week": "r604800",
        "month": "r2592000"
      }
    }
  },
  "indeed": {
    "actor_id": "misceres/indeed-scraper",
    "enabled": true,
    "param_map": {
      "experience": {
        "internship": "internship",
        "entry": "entry_level",
        "mid": "mid_level",
        "senior": "senior_level",
        "lead": "senior_level",
        "executive": "senior_level"
      },
      "date_posted": {
        "any": "",
        "day": "1",
        "week": "7",
        "month": "30"
      }
    }
  }
}
```

---

## Feature List

### 1. Resume Upload
- Drag-and-drop or file-picker (PDF / DOCX).
- **Original file stored as a binary blob** in SQLite (`resume.file_data`) and also written to `uploads/` folder.
- Extracted text stored separately for scoring.
- User can download the stored original at any time.
- User can replace the resume; previous version is archived (not deleted).

### 2. Search Configuration Panel

```
Role(s):        [Backend Engineer ×][Data Engineer ×][+Add]
Location:       [San Francisco, CA]          ☐ Remote only
Country:        [United States ▾]
Experience:     [Senior (5–8 yrs) ▾]
Employment:     ☑ Full-time  ☑ Contract  ☐ Part-time  ☐ Internship
Date Posted:    [Last 7 days ▾]
Salary (min):   [$120,000]  Currency: [USD ▾]
Max results/portal: [──●─────] 50

Portals (select all / deselect all):
☑ LinkedIn  ☑ Indeed  ☑ Glassdoor  ☑ ZipRecruiter  ☑ Monster
☑ SimplyHired  ☑ CareerBuilder  ☑ Dice  ☑ Wellfound
☑ RemoteOK  ☑ WeWorkRemotely  ☑ Greenhouse  ☑ Lever
☑ Workday  ☑ Naukri  ☑ Reed  ☑ Totaljobs

Resume:  [resume.pdf ✓]  [Replace]  [Download]

                               [   FIND JOBS   ]
```

### 3. Find Button
- Builds one Apify input payload per selected portal (using `portal_param_map`).
- Runs all actors in parallel via `ThreadPoolExecutor`.
- Per-portal progress bar updates via SSE (Server-Sent Events).
- Deduplicates across portals by `(company_name, title, location)` — keeps highest-score copy.

### 4. Results Table

| # | Company | Role Title | Experience | Fit Score | Job Description | Apply |
|---|---|---|---|---|---|---|
| Rank | Name + portal badge | Exact title | Level chip | Badge 0–100 % | 2-line excerpt + Read More | Apply → |

- **Fit Score badge** — Green ≥ 75 %, Yellow 50–74 %, Red < 50 %.
- **Read More** — inline expansion showing full JD; no page navigation.
- **Sortable** by Fit Score, Date Posted, Company (client-side, instant).
- **Filterable** by portal, experience level, employment type (client-side chips).
- **Pagination** — 25 rows per page; "Load all" option.

### 5. Saved / Bookmarked Jobs
- Star icon per row; stored in `job.saved` column.
- **Saved Jobs** tab.

### 6. Search History
- Every search logged with full parameter snapshot (JSON).
- Re-run with one click; parameters pre-filled.

---

## Data Flow

```
User fills form + uploads resume
        │
        ▼
POST /api/resume  ──► store original file blob + extracted text
POST /api/search  ──► validate & persist search params
        │
        ▼
ThreadPoolExecutor — one thread per selected portal
  ├── build_apify_input(portal, search_params)   [uses portal_param_map]
  ├── ApifyClient.actor(actor_id).call(input)
  └── stream items from default dataset
        │
        ▼
Normalise each item → JobRecord
  { portal, external_id, title, company, location, experience,
    description, url, posted_at, salary, employment_type }
        │
        ▼
Deduplicate by (company, title, location) across portals
        │
        ▼
Fit Scorer
  1. TF-IDF cosine(resume_text, job_text) → raw_score 0–1
  2. Multiply × 100, round → fit_score int
  3. Claude API: short 1-sentence fit rationale  [async, non-blocking]
        │
        ▼
Persist to SQLite, emit SSE progress event
        │
        ▼
GET /api/search/<id>/results  ──► paginated JSON (sorted by fit_score desc)
        │
        ▼
Frontend renders / updates table live
```

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/resume` | Upload / replace resume (multipart) |
| `GET` | `/api/resume` | Current resume metadata |
| `GET` | `/api/resume/download` | Download original file |
| `POST` | `/api/search` | Start search; returns `search_id` |
| `GET` | `/api/search/<id>/stream` | SSE stream — progress events per portal |
| `GET` | `/api/search/<id>/results` | Paginated results (`?page=1&per_page=25&sort=fit_score`) |
| `POST` | `/api/jobs/<id>/save` | Toggle save |
| `GET` | `/api/saved` | Saved jobs list |
| `GET` | `/api/history` | Past searches |
| `GET` | `/api/portals` | List all configured portals + enabled state |
| `GET` | `/` | SPA entry point |

---

## Database Schema (SQLite)

```sql
-- Resume versions (latest is max id)
CREATE TABLE resume (
    id          INTEGER PRIMARY KEY,
    filename    TEXT NOT NULL,
    file_data   BLOB NOT NULL,          -- original binary
    file_path   TEXT NOT NULL,          -- path in uploads/
    mime_type   TEXT NOT NULL,
    raw_text    TEXT NOT NULL,          -- extracted for scoring
    uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Search sessions
CREATE TABLE search (
    id              INTEGER PRIMARY KEY,
    resume_id       INTEGER REFERENCES resume(id),
    roles           TEXT NOT NULL,      -- JSON array
    location        TEXT,
    country         TEXT,
    remote_only     INTEGER DEFAULT 0,
    experience      TEXT,               -- internship|entry|mid|senior|lead|executive
    employment_type TEXT,               -- JSON array
    date_posted     TEXT,               -- any|day|week|month
    salary_min      INTEGER,
    salary_currency TEXT DEFAULT 'USD',
    max_results     INTEGER DEFAULT 50,
    portals         TEXT NOT NULL,      -- JSON array of portal keys
    status          TEXT DEFAULT 'pending', -- pending|running|done|error
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Individual job listings
CREATE TABLE job (
    id              INTEGER PRIMARY KEY,
    search_id       INTEGER REFERENCES search(id),
    portal          TEXT NOT NULL,
    external_id     TEXT,
    title           TEXT NOT NULL,
    company         TEXT NOT NULL,
    location        TEXT,
    experience      TEXT,
    employment_type TEXT,
    description     TEXT,
    salary_text     TEXT,
    url             TEXT NOT NULL,
    posted_at       DATETIME,
    fit_score       REAL,
    fit_rationale   TEXT,               -- Claude one-sentence explanation
    saved           INTEGER DEFAULT 0,
    dedup_key       TEXT                -- hash(company+title+location) for dedup
);

CREATE INDEX idx_job_search   ON job(search_id);
CREATE INDEX idx_job_score    ON job(search_id, fit_score DESC);
CREATE INDEX idx_job_dedup    ON job(search_id, dedup_key);
```

---

## Fit Scoring Algorithm

1. On upload, extract full text from resume (`pdfminer` / `python-docx`).
2. For each job: concatenate `title + " " + description`.
3. **Phase 1 (instant):** Fit both texts into a `TfidfVectorizer` → cosine similarity → `fit_score` (0–100 int). Written immediately when the job arrives.
4. **Phase 2 (async, free):** A background thread encodes both texts with `sentence-transformers` (`all-MiniLM-L6-v2`, runs locally) → semantic cosine similarity → overwrites `fit_score`. A keyword-overlap one-sentence rationale is generated without any API call and stored in `fit_rationale`.
5. The frontend polls `/api/jobs/<id>/score` and refreshes the badge + rationale in-place once Phase 2 completes.
6. **Phase 2 (future upgrade — Claude API):** The Claude-based scoring logic is preserved in a commented-out block in `app/services/scorer.py`. To enable: uncomment the block and set `ANTHROPIC_API_KEY` in `.env`.

---

## Configuration / Environment Variables (`.env`)

```
# Dev mode — no paid keys needed
APIFY_MOCK=true                        # true = fake data; false = real Apify calls
FLASK_SECRET_KEY=change_me
UPLOAD_FOLDER=uploads
DATABASE_URL=sqlite:///jobhunt.db
MAX_RESULTS_DEFAULT=50

# Uncomment when ready for real scraping:
# APIFY_API_TOKEN=apify_api_xxxxxxxxxxxx

# Uncomment when ready to upgrade to Claude-based scoring:
# ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxx
```

---

## Project File Structure

```
jobs-hunt/
├── app/
│   ├── __init__.py          # Flask app factory
│   ├── models.py            # SQLAlchemy models
│   ├── routes/
│   │   ├── resume.py        # /api/resume endpoints
│   │   ├── search.py        # /api/search endpoints
│   │   └── jobs.py          # /api/jobs, /api/saved, /api/history
│   ├── services/
│   │   ├── apify_service.py # Actor runner + normaliser
│   │   ├── scorer.py        # TF-IDF + Claude scoring
│   │   └── resume_parser.py # PDF / DOCX text extraction
│   └── static/
│       ├── index.html
│       ├── app.js
│       └── style.css
├── config/
│   └── portals.json         # Actor slugs + param_maps per portal
├── uploads/                 # Original resume files
├── .env                     # Secrets (git-ignored)
├── requirements.txt
└── run.py
```

---

## Out of Scope (v1)

- Scheduled / background monitoring (cron).
- Email / push notifications.
- Multi-user / OAuth.
- Mobile native app.

---

## Open Questions for Review

1. **Fit scoring default** — show TF-IDF score instantly while Claude score loads async, or wait for Claude? (Recommended: TF-IDF first, Claude updates badge in-place.)
2. **Apify billing** — each actor run consumes Apify credits. Cap per-portal `maxItems` at 50 by default; expose a slider so the user can raise/lower it.
3. **SSE vs polling** — SSE for live progress (recommended); falls back to 2 s polling if EventSource unavailable.
4. **Resume versioning** — keep all uploaded versions (auditable) or replace-in-place? (Spec v1.1: keep all, show latest by default.)
5. **Naukri / Reed / Totaljobs** — geo-specific portals enabled by default only if `country` matches (IN / GB). Toggle off for US-only searches automatically?

---

*Spec version: 1.1 — 2026-04-14*
