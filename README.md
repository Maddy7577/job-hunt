# Job Hunt

A Flask web application that fans out job searches across 17 job portals via Apify actors, scores results against your uploaded resume, and presents a ranked table.

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env — for local dev, APIFY_MOCK=true requires no API keys

# 3. Run
python run.py
```

App is served at `http://localhost:5060`.

## Features

- Search across 17 job portals simultaneously
- Upload a resume (PDF or DOCX) for automatic fit scoring
- Two-phase scoring: instant TF-IDF + async semantic scoring (sentence-transformers, free & local)
- Save and track jobs; view search history
- Mock mode for development — no Apify credits consumed

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `FLASK_SECRET_KEY` | Yes | Any secret string |
| `APIFY_MOCK` | No | `true` (default) — use fake data; `false` — real scraping |
| `APIFY_API_TOKEN` | When mock=false | Apify API token |
| `ANTHROPIC_API_KEY` | No | Enables Claude-based scoring (paid) |

## Project Structure

```
app/
  __init__.py          # Flask app factory
  models.py            # SQLAlchemy models: Resume, Search, Job
  routes/              # API blueprints (resume, search, jobs)
  services/            # apify_service, scorer, resume_parser
  static/              # index.html, app.js, style.css (SPA)
config/
  portals.json         # Portal config — add/remove portals here
.claude/
  specs/               # App specification + per-feature spec files
  commands/            # Custom Claude Code slash commands
  ideation/            # Feature ideation prompts
```

See `CLAUDE.md` for full architecture details and the feature development workflow.

## Feature Development Workflow

New features follow an ideation-first, spec-driven process using Claude Code:

1. Describe the feature in plain language to Claude Code.
2. Claude distills it into a workable prompt saved to `.claude/ideation/feature-idea.md`.
3. Review and adjust `feature-idea.md` if needed.
4. Run `/feature-create-spec <step> <feature-name>` — Claude generates a detailed spec at `.claude/specs/<step>-<feature-slug>.md`.
5. Review the spec, then enter Plan mode to begin implementation.
