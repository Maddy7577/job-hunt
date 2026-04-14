# Feature Idea: AutoHunt — Personal Auto-Hunt

## Name
**AutoHunt** *(automated job hunting, pre-configured for you — no setup needed)*

## One-line Summary
A dedicated, pre-configured "find jobs for me" tab that fires a global job search tuned to Maddy's exact profile with one click — no form-filling, instant results.

---

## What It Does

Orion is a personal, locked-profile search mode that lives as a top-level tab alongside the main search. Instead of a general-purpose search form, it presents a minimal UI pre-loaded with the user's permanent profile and a single **Hunt** button.

### Pre-configured Profile (persisted, not ephemeral)
| Field | Value |
|---|---|
| Current location | Pune, India |
| Experience | 11+ years (maps to `lead` level in portals) |
| Work location preference | **Open to everything** — India, abroad, remote |
| Skills (tag input, editable) | `Test Manager`, `Worksoft Certify`, `Agentic AI`, `Claude` *(defaults; user can add/remove)* |
| Language filter | English-only (filter out roles requiring non-English proficiency) |
| Visa filter | Filter out roles in regions that require local residency/work authorisation **without** offering visa sponsorship |

### Location Strategy
- Pass `remote: true` and `location: "India"` to actors that support it.
- For actors that take a single location, fan out two parallel runs: one with `India` and one with `remote`.
- Do **not** restrict to India-only; include all portals globally (including Naukri, LinkedIn, Indeed, Glassdoor, RemoteOK, WeWorkRemotely, etc.).

### Post-fetch Filtering (applied after Apify results arrive)
Two lightweight text-scan passes on the job description before the row is saved or displayed:

1. **Language filter** — drop any listing whose description contains phrases like *"fluent in [non-English language]"*, *"German required"*, *"French mandatory"*, *"native [non-English] speaker"*, etc. Implement as a small regex/keyword blocklist.

2. **Visa/residency filter** — drop listings that match phrases like *"must be authorised to work in [country]"*, *"no visa sponsorship"*, *"citizens only"*, *"permanent residents only"*, *"right to work in [country] required"* — **unless** the listing also contains a phrase indicating sponsorship is available (*"visa sponsorship provided"*, *"we sponsor visas"*, *"open to relocation assistance"*). Implement as a two-pass regex: blocklist check first, allowlist override second.

### Skills Input (Orion-specific)
- Same multi-tag UX as the main search's Roles field.
- Default tags on first load: `Test Manager`, `Worksoft Certify`, `Agentic AI`, `Claude`.
- Tags are stored in browser localStorage (or a dedicated `orion_profile` table in SQLite) so edits persist across sessions.
- Skills are used as the **keywords/roles** sent to Apify actors (same `roles` field, multi-value).

---

## UI Layout

```
[ Main Search ]  [ AutoHunt ]  [ Saved ]  [ History ]    ← top nav tabs

┌─────────────────────────────────────────────────────┐
│  AUTOHUNT — Personal Hunt                           │
│                                                     │
│  Skills:  [Test Manager ×][Worksoft Certify ×]      │
│           [Agentic AI ×][Claude ×][+ Add skill]     │
│                                                     │
│  📍 Pune, India · 11+ yrs · Open to world           │
│  🌐 All portals · English-only · Visa-friendly      │
│                                                     │
│                    [ HUNT ]                         │
└─────────────────────────────────────────────────────┘

  ↓  Results (same table as main search):

  #  Company          Role Title       Experience  Fit Score  JD          Apply
  1  Acme Corp        Test Manager     Lead        ████ 91%   Read More   Apply →
  2  Globex Inc       QA Architect     Lead        ███  78%   Read More   Apply →
```

### Results Table Column Order
Identical to the main search table:
`# | Company (+ portal badge) | Role Title | Experience chip | Fit Score badge | Job Description (Read More) | Apply →`

- Fit Score badge: Green ≥ 75%, Yellow 50–74%, Red < 50%.
- Sortable by Fit Score, Date Posted, Company (client-side).
- Filterable by portal chip.
- Pagination: 25 per page.
- Star/bookmark per row (same saved-jobs mechanism).

---

## Backend Changes

### New route: `/api/autohunt`
- `GET /api/autohunt/profile` — return stored AutoHunt skills list.
- `PUT /api/autohunt/profile` — update skills list (array of strings).
- `POST /api/autohunt/hunt` — trigger a hunt; internally builds a `Search` record with AutoHunt's pre-set params and kicks off the same `ThreadPoolExecutor` fan-out used by the main search. Returns `search_id`.
- Reuses `GET /api/search/<id>/stream` and `GET /api/search/<id>/results` for SSE progress and results — no new polling endpoints needed.

### New model / storage
- Add `AutoHuntProfile` table (or a JSON config row) with `skills` (JSON array). Seeded with defaults on first run.
- Alternatively: store in a single row of a `settings` key-value table keyed by `autohunt_skills`.

### Filter service: `app/services/autohunt_filter.py`
```python
LANGUAGE_BLOCK = re.compile(
    r'\b(fluent|native|proficient|required|mandatory)\b.{0,30}'
    r'\b(german|french|spanish|dutch|portuguese|italian|mandarin|japanese|arabic|hindi|'
    r'korean|russian|turkish|polish|swedish|norwegian|danish|finnish)\b',
    re.IGNORECASE
)

VISA_BLOCK = re.compile(
    r'\b(must be (authorised|authorized|eligible) to work|'
    r'no visa sponsorship|citizens only|permanent residents? only|'
    r'right to work in [a-z]+ required|work permit required)\b',
    re.IGNORECASE
)

VISA_ALLOW = re.compile(
    r'\b(visa sponsorship (provided|available|offered)|'
    r'we (sponsor|provide) visas?|open to (relocation|sponsorship))\b',
    re.IGNORECASE
)

def should_include(description: str) -> bool:
    if LANGUAGE_BLOCK.search(description):
        return False
    if VISA_BLOCK.search(description):
        if not VISA_ALLOW.search(description):
            return False
    return True
```

Called inside the job-normalisation loop in `apify_service.py` before inserting a `Job` row.

---

## Portals Used
All 17 portals from `config/portals.json`, with special attention to:
- **Naukri** (India-local roles)
- **LinkedIn** (global, India office + remote)
- **RemoteOK** / **WeWorkRemotely** (fully remote roles worldwide)
- **Greenhouse / Lever / Workday** (enterprise global roles)

---

## Out of Scope for This Feature
- Scheduled / automatic daily runs (can be a follow-up cron feature).
- Email notifications on new results.
- Separate Orion scoring weights (uses same TF-IDF + sentence-transformers pipeline).

---

*Feature idea version: 1.0 — 2026-04-14*
