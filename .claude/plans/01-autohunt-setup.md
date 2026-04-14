# Implementation Plan: 01 — Auto Hunt Set Up

## Context
AutoHunt is a personal, zero-configuration job-search tab pre-wired to Maddy's fixed profile (Pune, India · 11+ yrs · global/remote openness). The user edits a persisted skills list and clicks **Hunt**. The backend fans out across all 17 enabled Apify portals, applies two regex-based filters (language exclusion, visa/residency exclusion), scores results, and streams live progress via SSE — reusing the existing search pipeline end-to-end.

---

## Implementation Order

### Step 1 — `app/models.py`: Add `AutoHuntProfile` model + `autohunt_filtered` column

**Add `AutoHuntProfile` model** (append after `Job`):
```python
class AutoHuntProfile(db.Model):
    __tablename__ = "autohunt_profile"
    id         = db.Column(db.Integer, primary_key=True)
    skills     = db.Column(db.Text, nullable=False)   # JSON array
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

**Add `autohunt_filtered` column to `Job`** (after `dedup_key`):
```python
autohunt_filtered = db.Column(db.Integer, default=0)
```

**Update `Job.to_dict()`** — add at the end of the returned dict:
```python
"autohunt_filtered": bool(self.autohunt_filtered),
```

> After this step, reset the DB: `flask shell` → `from app import db; db.drop_all(); db.create_all()`

---

### Step 2 — Create `app/services/autohunt_filter.py`

New file. Pure Python — no Flask context, importable standalone.

```python
import re

_LANGUAGE_BLOCK = re.compile(
    r'\b(fluent|native|proficient|required?|mandatory)\b.{0,40}'
    r'\b(german|french|spanish|dutch|portuguese|italian|mandarin|cantonese|'
    r'japanese|arabic|hindi|korean|russian|turkish|polish|swedish|norwegian|'
    r'danish|finnish|czech|romanian|hungarian|greek|hebrew|thai|vietnamese)\b',
    re.IGNORECASE,
)

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
    if not description:
        return True
    if _LANGUAGE_BLOCK.search(description):
        return False
    if _VISA_BLOCK.search(description):
        if not _VISA_ALLOW.search(description):
            return False
    return True
```

---

### Step 3 — Create `app/routes/autohunt.py`

New file. Blueprint with three routes + background worker.

**Reuse from existing code:**
- `_push()` imported from `app.routes.search` (shares the same `_sse_queues` dict — no duplication)
- `load_portals_config()` from `app.services.apify_service`
- `run_search()` from `app.services.apify_service`
- `tfidf_score()` + `semantic_score_async()` from `app.services.scorer`

**Fixed profile constants** (module-level):
```python
_AUTOHUNT_LOCATION   = "Pune, India"
_AUTOHUNT_COUNTRY    = "IN"
_AUTOHUNT_EXPERIENCE = "lead"
_AUTOHUNT_MAX        = 50
_DEFAULT_SKILLS      = ["Test Manager", "Worksoft Certify", "Agentic AI", "Claude"]
```

**Routes:**
- `GET /api/autohunt/profile` → seed on first call if no row; return `{"skills": [...]}`
- `PUT /api/autohunt/profile` → validate list, strip whitespace, reject empty strings, commit
- `POST /api/autohunt/hunt` → require resume + non-empty skills; build `Search` record; spawn `_execute_autohunt` thread; return `202 {"search_id": N}`

**`_execute_autohunt(search_id, resume, portals, params, app)`** mirrors `_execute_search` in `search.py` with one addition: before creating a `Job` row, call `should_include(job_data["description"])`. If filtered, set `autohunt_filtered=1` and `fit_score=None`; skip SSE `job_added` event and skip scoring calls.

**params dict passed to `run_search()`:**
```python
{
    "roles": skills,
    "location": "Pune, India",
    "country": "IN",
    "remote_only": False,       # search both local + remote
    "experience": "lead",
    "employment_type": ["full-time", "contract"],
    "date_posted": "any",
    "max_results": 50,
    "autohunt_mode": True,      # informational flag
}
```

---

### Step 4 — `app/__init__.py`: Register blueprint

Add alongside the existing three blueprint registrations:
```python
from app.routes.autohunt import autohunt_bp
app.register_blueprint(autohunt_bp)
```

---

### Step 5 — `app/routes/search.py`: Filter excluded jobs from results

In `results()` (`GET /api/search/<id>/results`), add optional exclusion of filtered jobs:
```python
exclude_filtered = request.args.get("exclude_filtered", "1") == "1"

query = Job.query.filter_by(search_id=search_id)
if exclude_filtered:
    query = query.filter_by(autohunt_filtered=0)
pagination = query.order_by(sort_col).paginate(...)
```

Default is `?exclude_filtered=1` (excluded). Passing `?exclude_filtered=0` shows all rows. This is backward-compatible: existing main-search calls don't pass the param, so they now get the default `1` — but since main-search jobs always have `autohunt_filtered=0`, the filter has no effect on them.

---

### Step 6 — `app/static/index.html`: Add AutoHunt tab + panel

**Nav tab** — add after the existing Search nav item:
```html
<li class="nav-item">
  <a class="nav-link" data-tab="autohunt" href="#">AutoHunt</a>
</li>
```

**Tab panel** — add after `#tab-search` div:
```html
<div id="tab-autohunt" class="tab-content container-fluid py-4 d-none">
  <div class="card shadow-sm p-4 mb-4">
    <h5 class="fw-semibold mb-3">AutoHunt — Personal Hunt</h5>

    <label class="form-label fw-medium">Skills</label>
    <div id="ahSkillsContainer" class="d-flex flex-wrap gap-2 mb-2"></div>
    <div class="d-flex gap-2 mb-3">
      <input type="text" id="ahSkillInput" class="form-control" placeholder="Add a skill…" />
      <button class="btn btn-outline-secondary" id="ahAddSkillBtn">
        <i class="bi bi-plus"></i> Add
      </button>
    </div>

    <p class="text-muted small mb-3">
      📍 Pune, India &nbsp;·&nbsp; 11+ yrs &nbsp;·&nbsp;
      Open to world &nbsp;·&nbsp; English-only &nbsp;·&nbsp; Visa-friendly
    </p>

    <button id="ahHuntBtn" class="btn btn-primary px-5">HUNT</button>
  </div>

  <div id="ahProgress" class="d-none mb-4"></div>
  <div id="ahResultsSection" class="d-none">
    <div class="d-flex justify-content-between align-items-center mb-2">
      <span id="ahResultsSummary" class="text-muted small"></span>
    </div>
    <div class="table-responsive">
      <table class="table table-hover align-middle">
        <thead class="table-light">
          <tr>
            <th>#</th><th>Company</th><th>Role</th><th>Experience</th>
            <th>Fit Score</th><th>Description</th><th>Apply</th><th></th>
          </tr>
        </thead>
        <tbody id="ahResultsBody"></tbody>
      </table>
    </div>
    <div class="d-flex justify-content-between align-items-center mt-2">
      <button id="ahPrevBtn" class="btn btn-sm btn-outline-secondary" disabled>← Prev</button>
      <span id="ahPageInfo" class="text-muted small"></span>
      <button id="ahNextBtn" class="btn btn-sm btn-outline-secondary" disabled>Next →</button>
    </div>
  </div>
</div>
```

---

### Step 7 — `app/static/app.js`: AutoHunt module

Add a self-contained AutoHunt block at the end of `app.js`. **Reuse** these existing helpers:
- `$()` — DOM selection shorthand
- `scoreClass(s)` / `scoreBadge(s)` — fit score badge HTML
- `portalBadge(p)` — portal label
- `escHtml()` / `escAttr()` — XSS protection
- `showToast(msg, type)` — notifications
- `bindStarBtn(btn)` — save/bookmark toggle
- `openJdModal(job)` — full JD modal
- `startScorePoller(jobId)` — async score polling

**AutoHunt state:**
```javascript
const ahState = { skills: [], searchId: null, currentPage: 1, totalPages: 1 };
```

**Functions to implement:**

1. **`ahRenderSkills()`** — Regenerate `#ahSkillsContainer` chips from `ahState.skills` (same badge+btn-close pattern as `renderRoles()`).

2. **`ahAddSkill()`** — Read `#ahSkillInput`, trim, skip duplicates/empty, push to `ahState.skills`, call `ahSaveProfile()`, re-render.

3. **`ahSaveProfile()`** — `PUT /api/autohunt/profile` with `{skills: ahState.skills}`.

4. **`ahLoadProfile()`** — `GET /api/autohunt/profile`; populate `ahState.skills`; call `ahRenderSkills()`.

5. **`ahStartHunt()`** — Disable `#ahHuntBtn`, show `#ahProgress`, clear `#ahResultsBody`. `POST /api/autohunt/hunt`. On 202, save `search_id`, call `ahOpenSSE(searchId)`.

6. **`ahSetupPortalProgress(portals)`** — Render progress bar rows into `#ahProgress` (same structure as `showProgressSection(portals)`).

7. **`ahOpenSSE(searchId)`** — `new EventSource("/api/search/${searchId}/stream")`. Handlers:
   - `portal_done` → mark portal bar done/error
   - `job_added` → append row via `ahAppendJobRow(job_data)` (or load first page on first job)
   - `status` (done) → re-enable `#ahHuntBtn`, show `#ahResultsSection`, call `ahLoadPage(1)`
   - `__done__` → `evtSource.close()`

8. **`ahLoadPage(page)`** — `GET /api/search/${ahState.searchId}/results?page=${page}&exclude_filtered=1`. Render rows into `#ahResultsBody` using same column order as main search. Update pagination controls.

9. **`ahRenderRow(job, idx)`** — Build `<tr>` with: `#`, company+portal badge, title, experience badge, `scoreBadge()`, 180-char excerpt + Read More, Apply button, star button. Call `bindStarBtn()` and (if no rationale) `startScorePoller()`.

**Wire up on DOMContentLoaded:**
```javascript
$("ahAddSkillBtn").addEventListener("click", ahAddSkill);
$("ahSkillInput").addEventListener("keydown", e => e.key === "Enter" && ahAddSkill());
$("ahHuntBtn").addEventListener("click", ahStartHunt);
$("ahPrevBtn").addEventListener("click", () => ahLoadPage(ahState.currentPage - 1));
$("ahNextBtn").addEventListener("click", () => ahLoadPage(ahState.currentPage + 1));
```

**Hook tab activation** — inside `switchTab()` (or add to the tab-click event listener), add:
```javascript
if (name === "autohunt") ahLoadProfile();
```

---

### Step 8 — `app/static/style.css`: AutoHunt-specific styles

No new CSS variables needed (Bootstrap 5 handles everything). Add minimal rules for the fixed profile meta line only:
```css
/* AutoHunt */
#tab-autohunt .text-muted.small { font-size: 0.82rem; }
```

All card, badge, button, table, and progress-bar styling reuses existing Bootstrap classes already in use.

---

## Files Changed / Created

| Action | File |
|---|---|
| Modify | `app/models.py` |
| Modify | `app/__init__.py` |
| Modify | `app/routes/search.py` |
| Modify | `app/static/index.html` |
| Modify | `app/static/app.js` |
| Modify | `app/static/style.css` |
| Create | `app/routes/autohunt.py` |
| Create | `app/services/autohunt_filter.py` |

---

## DB Reset Required

After `app/models.py` changes, reset the SQLite DB:
```bash
flask shell
>>> from app import db; db.drop_all(); db.create_all()
>>> exit()
```

---

## Verification (Definition of Done)

Run `python run.py` (mock mode, `APIFY_MOCK=true`) and verify:

- [ ] `GET /api/autohunt/profile` → `{"skills": ["Test Manager", "Worksoft Certify", "Agentic AI", "Claude"]}` on fresh DB
- [ ] `PUT /api/autohunt/profile {"skills":["QA Lead"]}` → reflected on next GET
- [ ] `POST /api/autohunt/hunt` with no resume → `400`
- [ ] `POST /api/autohunt/hunt` with resume → `202 {"search_id": N}`
- [ ] SSE stream shows `portal_done` events for all enabled portals, then `status: done`
- [ ] `GET /api/search/<id>/results` returns only `autohunt_filtered=0` jobs
- [ ] AutoHunt tab visible in nav; clicking it activates the panel and loads skills
- [ ] Skills tag input pre-populates with defaults on first load; edits survive page refresh
- [ ] HUNT button shows portal progress bars, then populates results table
- [ ] Results columns in order: `# | Company | Role | Experience | Fit Score | JD | Apply | ★`
- [ ] Fit score badges: green ≥75%, orange 50–74%, red <50%
- [ ] Main search tab and all existing API endpoints unaffected
