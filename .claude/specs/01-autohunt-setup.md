# Spec 01: Auto Hunt Set Up

## Overview
AutoHunt is a personal, pre-configured job-search tab built for a single user profile (Pune, India · 11+ years experience · open to global / remote work). Unlike the general search form, AutoHunt requires zero configuration: the user edits a short skills list and hits **Hunt**. Behind the scenes it builds a `Search` record using fixed profile constants, fans out across all 17 portals using the existing `ThreadPoolExecutor` pipeline, and applies two post-fetch filters (language exclusion, visa/residency exclusion) before persisting any `Job` row. Results are displayed in the same ranked table as the main search. This step establishes the data model, filter service, API routes, and the AutoHunt tab UI — the complete end-to-end flow from button click to visible results.

---

## Depends on
No previous feature steps required. Builds directly on the initial prototype (commit `8d7d32c`).

---

## Routes

| Method | Path | Description | Access |
|---|---|---|---|
| `GET` | `/api/autohunt/profile` | Return the stored AutoHunt skills list as a JSON array | public |
| `PUT` | `/api/autohunt/profile` | Replace the skills list; body: `{"skills": ["..."]}` | public |
| `POST` | `/api/autohunt/hunt` | Trigger an AutoHunt run; returns `{"search_id": N}` | public |

> The hunt reuses the existing `GET /api/search/<id>/stream` (SSE progress) and `GET /api/search/<id>/results` (paginated results) endpoints — no new polling routes needed.

---

## Database changes

### New table: `autohunt_profile`
Stores the persisted skills list (single-row settings pattern).

```python
class AutoHuntProfile(db.Model):
    __tablename__ = "autohunt_profile"

    id          = db.Column(db.Integer, primary_key=True)
    skills      = db.Column(db.Text, nullable=False)   # JSON array of skill strings
    updated_at  = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

- Seeded on first `GET /api/autohunt/profile` if the table is empty with default skills:
  `["Test Manager", "Worksoft Certify", "Agentic AI", "Claude"]`
- Always read/write the row with `id = 1` (single-row pattern — no multi-user support needed).

### New flag column on `job` table: `autohunt_filtered`
```python
autohunt_filtered = db.Column(db.Integer, default=0)  # 1 = dropped by AutoHunt filter
```
Filtered jobs are stored with this flag set to `1` and `fit_score = None` so they are excluded from results queries but remain auditable. This avoids silent data loss.

> **Important:** Add both changes to `app/models.py`. Run `db.drop_all(); db.create_all()` in `flask shell` to apply (dev-only; no migration tooling in scope).

---

## UI changes

### `app/static/index.html`
- Add an **AutoHunt** nav tab alongside the existing Main Search, Saved, and History tabs.
- Add the AutoHunt panel section (hidden by default, shown when tab is active):

```html
<!-- AutoHunt tab button -->
<li class="nav-item">
  <a class="nav-link" id="autohunt-tab" href="#autohunt-panel">AutoHunt</a>
</li>

<!-- AutoHunt panel -->
<div id="autohunt-panel" class="tab-pane">
  <div class="autohunt-card">
    <h5 class="autohunt-title">AutoHunt — Personal Hunt</h5>

    <!-- Skills multi-tag input -->
    <label class="form-label">Skills</label>
    <div id="autohunt-skills-container" class="tag-input-container"></div>

    <!-- Fixed profile metadata (read-only display) -->
    <p class="autohunt-meta">
      📍 Pune, India &nbsp;·&nbsp; 11+ yrs &nbsp;·&nbsp; Open to world
      &nbsp;·&nbsp; English-only &nbsp;·&nbsp; Visa-friendly
    </p>

    <button id="autohunt-hunt-btn" class="btn btn-primary btn-hunt">HUNT</button>
  </div>

  <!-- Progress + results reuse existing components -->
  <div id="autohunt-progress" class="portal-progress-container d-none"></div>
  <div id="autohunt-results-table" class="results-container d-none"></div>
</div>
```

### `app/static/app.js`
Add an `AutoHunt` module (self-contained, no changes to existing search logic):

1. **`loadAutoHuntProfile()`** — `GET /api/autohunt/profile` on tab activation; renders skill tags using the same tag-input pattern as the main search's Roles field.
2. **`saveAutoHuntProfile(skills)`** — `PUT /api/autohunt/profile` debounced on tag add/remove.
3. **`startAutoHunt()`** — `POST /api/autohunt/hunt`; on 202 response, subscribes to `GET /api/search/<id>/stream` (SSE) and renders progress bars into `#autohunt-progress`.
4. **`renderAutoHuntResults(searchId)`** — `GET /api/search/<id>/results`; renders into `#autohunt-results-table` using the same table-rendering helper used by the main search (extract or reuse `renderJobsTable(jobs, containerId)`).
5. Attach `startAutoHunt` to `#autohunt-hunt-btn` click.
6. Activate `loadAutoHuntProfile` when the AutoHunt tab is clicked.

### `app/static/style.css`
- `.autohunt-card` — white card with border-radius and padding, matching the existing search panel card style. Use existing CSS variables (`--card-bg`, `--border-radius`, `--spacing-md`).
- `.autohunt-title` — same font-weight/size as existing panel headings.
- `.autohunt-meta` — muted small text (use `--text-muted` variable) for the fixed profile line.
- `.btn-hunt` — reuse existing `.btn-primary`; no custom colour needed.

---

## Files to change

| File | Change |
|---|---|
| `app/models.py` | Add `AutoHuntProfile` model; add `autohunt_filtered` column to `Job` |
| `app/__init__.py` | Register `autohunt_bp` blueprint; ensure `AutoHuntProfile` table is created |
| `app/static/index.html` | Add AutoHunt nav tab + panel HTML |
| `app/static/app.js` | Add AutoHunt JS module (profile load/save, hunt trigger, SSE, results render) |
| `app/static/style.css` | Add AutoHunt panel styles using existing CSS variables |
| `app/services/apify_service.py` | Import and call `autohunt_filter.should_include()` inside `run_search()` when `autohunt_mode=True` is passed in `search_params` |

---

## Files to create

| File | Purpose |
|---|---|
| `app/routes/autohunt.py` | Blueprint with `GET/PUT /api/autohunt/profile` and `POST /api/autohunt/hunt` |
| `app/services/autohunt_filter.py` | `should_include(description: str) -> bool` — language + visa regex filters |

### `app/services/autohunt_filter.py` (full implementation)

```python
import re

# Drop roles requiring non-English language proficiency
_LANGUAGE_BLOCK = re.compile(
    r'\b(fluent|native|proficient|required?|mandatory)\b.{0,40}'
    r'\b(german|french|spanish|dutch|portuguese|italian|mandarin|cantonese|'
    r'japanese|arabic|hindi|korean|russian|turkish|polish|swedish|norwegian|'
    r'danish|finnish|czech|romanian|hungarian|greek|hebrew|thai|vietnamese)\b',
    re.IGNORECASE,
)

# Drop roles that restrict to local residents/citizens without sponsorship
_VISA_BLOCK = re.compile(
    r'\b('
    r'must be (authoris|authoriz)ed to work|'
    r'no visa sponsorship|'
    r'citizens? only|'
    r'permanent residents? only|'
    r'right to work in \w[\w\s]{0,20} required|'
    r'work permit required|'
    r'legally (authoris|authoriz)ed to work'
    r')\b',
    re.IGNORECASE,
)

# Override: listing explicitly offers sponsorship — do NOT drop
_VISA_ALLOW = re.compile(
    r'\b('
    r'visa sponsorship (provided|available|offered|considered)|'
    r'we (sponsor|provide|offer) visas?|'
    r'open to (relocation|sponsorship)|'
    r'sponsorship (is |will be )?(provided|available|considered)'
    r')\b',
    re.IGNORECASE,
)


def should_include(description: str) -> bool:
    """
    Return True if the job description passes AutoHunt filters.
    Return False if the listing requires a non-English language
    or restricts to local residents without offering visa sponsorship.
    """
    if not description:
        return True

    if _LANGUAGE_BLOCK.search(description):
        return False

    if _VISA_BLOCK.search(description):
        # Only keep if the listing also promises sponsorship
        if not _VISA_ALLOW.search(description):
            return False

    return True
```

### `app/routes/autohunt.py` (structure)

```python
import json
from datetime import datetime
from flask import Blueprint, request, jsonify, current_app
import threading

from app import db
from app.models import AutoHuntProfile, Resume, Search, Job
from app.services.apify_service import run_search, load_portals_config
from app.services.scorer import tfidf_score, semantic_score_async
from app.services.autohunt_filter import should_include
from app.routes.search import _push  # reuse SSE push helper

autohunt_bp = Blueprint("autohunt", __name__)

# ── Fixed profile constants ───────────────────────────────────────────
_AUTOHUNT_LOCATION   = "Pune, India"
_AUTOHUNT_COUNTRY    = "IN"
_AUTOHUNT_EXPERIENCE = "lead"           # 11+ yrs → lead level
_AUTOHUNT_MAX        = 50
_DEFAULT_SKILLS      = ["Test Manager", "Worksoft Certify", "Agentic AI", "Claude"]


def _get_or_create_profile() -> AutoHuntProfile:
    profile = AutoHuntProfile.query.get(1)
    if not profile:
        profile = AutoHuntProfile(id=1, skills=json.dumps(_DEFAULT_SKILLS))
        db.session.add(profile)
        db.session.commit()
    return profile


@autohunt_bp.route("/api/autohunt/profile", methods=["GET"])
def get_profile():
    profile = _get_or_create_profile()
    return jsonify({"skills": json.loads(profile.skills)})


@autohunt_bp.route("/api/autohunt/profile", methods=["PUT"])
def update_profile():
    body = request.get_json(force=True) or {}
    skills = body.get("skills", [])
    if not isinstance(skills, list):
        return jsonify({"error": "skills must be a list"}), 400
    profile = _get_or_create_profile()
    profile.skills = json.dumps([str(s).strip() for s in skills if str(s).strip()])
    profile.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"skills": json.loads(profile.skills)})


@autohunt_bp.route("/api/autohunt/hunt", methods=["POST"])
def start_hunt():
    resume = Resume.query.order_by(Resume.id.desc()).first()
    if not resume:
        return jsonify({"error": "Upload a resume first"}), 400

    profile = _get_or_create_profile()
    skills = json.loads(profile.skills)
    if not skills:
        return jsonify({"error": "Add at least one skill before hunting"}), 400

    cfg = load_portals_config()
    portals = [k for k, v in cfg.items() if v.get("enabled", True)]

    search = Search(
        resume_id=resume.id,
        roles=json.dumps(skills),
        location=_AUTOHUNT_LOCATION,
        country=_AUTOHUNT_COUNTRY,
        remote_only=0,          # we want both local+remote, not remote-only
        experience=_AUTOHUNT_EXPERIENCE,
        employment_type=json.dumps(["full-time", "contract"]),
        date_posted="any",
        salary_min=None,
        salary_currency="USD",
        max_results=_AUTOHUNT_MAX,
        portals=json.dumps(portals),
        status="pending",
    )
    db.session.add(search)
    db.session.commit()

    search_id = search.id
    app = current_app._get_current_object()

    params = {
        "roles": skills,
        "location": _AUTOHUNT_LOCATION,
        "country": _AUTOHUNT_COUNTRY,
        "remote_only": False,
        "experience": _AUTOHUNT_EXPERIENCE,
        "employment_type": ["full-time", "contract"],
        "date_posted": "any",
        "max_results": _AUTOHUNT_MAX,
        "autohunt_mode": True,   # signals filter layer to apply AutoHunt filters
    }

    t = threading.Thread(
        target=_execute_autohunt,
        args=(search_id, resume, portals, params, app),
        daemon=True,
    )
    t.start()

    return jsonify({"search_id": search_id}), 202


def _execute_autohunt(search_id, resume, portals, params, app):
    """Mirrors _execute_search in search.py but applies AutoHunt filters."""
    with app.app_context():
        search = db.session.get(Search, search_id)
        search.status = "running"
        db.session.commit()
        _push(search_id, "status", {"status": "running", "portals": portals})

        def progress_cb(portal_key, status, count):
            _push(search_id, "portal_done", {
                "portal": portal_key, "status": status, "count": count,
            })

        try:
            jobs = run_search(params, portals, progress_cb=progress_cb)
        except Exception as exc:
            search.status = "error"
            db.session.commit()
            _push(search_id, "error", {"message": str(exc)})
            _push(search_id, "__done__", {})
            return

        resume_text = resume.raw_text
        kept = 0

        for job_data in jobs:
            filtered = not should_include(job_data.get("description", ""))
            score = None if filtered else tfidf_score(resume_text, f"{job_data['title']} {job_data['description']}")

            job = Job(
                search_id=search_id,
                portal=job_data["portal"],
                external_id=job_data["external_id"],
                title=job_data["title"],
                company=job_data["company"],
                location=job_data["location"],
                experience=job_data["experience"],
                employment_type=job_data["employment_type"],
                description=job_data["description"],
                salary_text=job_data["salary_text"],
                url=job_data["url"],
                posted_at=job_data["posted_at"],
                fit_score=score,
                dedup_key=job_data["dedup_key"],
                autohunt_filtered=1 if filtered else 0,
            )
            db.session.add(job)
            db.session.flush()

            if not filtered:
                kept += 1
                _push(search_id, "job_added", {
                    "job_id": job.id, "title": job.title,
                    "company": job.company, "fit_score": score,
                })
                semantic_score_async(job.id, resume_text,
                                     f"{job_data['title']} {job_data['description']}", app)

        db.session.commit()
        search.status = "done"
        db.session.commit()
        _push(search_id, "status", {"status": "done", "total": kept})
        _push(search_id, "__done__", {})
```

---

## New dependencies
No new dependencies. All regex, SQLAlchemy, threading, and Flask primitives are already in use.

---

## Rules for implementation
- Use SQLAlchemy models; never write raw SQL.
- Use CSS variables — never hardcode hex values.
- Portal config belongs in `config/portals.json`, not in Python code.
- Mock mode must remain functional after the change (`APIFY_MOCK=true`).
- No breaking changes to existing API response shapes.
- The `autohunt_filter` module must be importable standalone (no Flask app context required) — pure regex, no DB calls.
- `_push()` is imported from `app.routes.search` — do not duplicate the SSE queue logic.
- The `autohunt_filtered` column must be added to `Job.to_dict()` so the frontend can verify filter counts if needed (add `"autohunt_filtered": bool(self.autohunt_filtered)`).
- The results endpoint (`GET /api/search/<id>/results`) must **exclude** filtered jobs by default: add `filter_by(autohunt_filtered=0)` in the query when `autohunt_filtered` column exists. Since this endpoint is shared, add it as an optional query param: `?exclude_filtered=1` (default `1`).
- The fixed profile constants (`_AUTOHUNT_LOCATION`, `_AUTOHUNT_EXPERIENCE`, etc.) live in `app/routes/autohunt.py` as module-level constants — not in `config/portals.json` (they are user-specific, not portal-specific).
- Skills list must reject empty strings and strip whitespace before saving.

---

## Definition of done

- [ ] `GET /api/autohunt/profile` returns `{"skills": ["Test Manager", "Worksoft Certify", "Agentic AI", "Claude"]}` on a fresh DB.
- [ ] `PUT /api/autohunt/profile` with `{"skills": ["QA Lead"]}` is reflected by a subsequent `GET`.
- [ ] `POST /api/autohunt/hunt` with no resume returns `400`.
- [ ] `POST /api/autohunt/hunt` with a resume returns `202` and a `search_id`.
- [ ] Subscribing to `GET /api/search/<id>/stream` after a hunt shows `portal_done` events for all enabled portals and a final `status: done` event.
- [ ] `GET /api/search/<id>/results` returns only jobs where `autohunt_filtered = 0`.
- [ ] AutoHunt tab is visible in the nav and activates its panel.
- [ ] Skills tag input pre-loads saved skills on tab activation.
- [ ] Adding/removing a skill tag persists after a page refresh.
- [ ] Clicking **HUNT** shows portal progress bars, then populates the results table with `# | Company | Role | Experience | Fit Score | JD | Apply` columns.
- [ ] Fit Score badges are green ≥ 75 %, yellow 50–74 %, red < 50 %.
- [ ] Mock mode (`APIFY_MOCK=true`) completes a full hunt cycle without errors.
- [ ] Main search tab and its API endpoints are unaffected.

---

*Spec version: 1.0 — 2026-04-14*
