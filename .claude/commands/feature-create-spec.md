---
description: Create a spec file for the feature discussed in feature-idea.md
argument-hint: "<step_number> <feature-name> e.g. 01 Resume Scoring"
allowed-tools: Read, Write, Glob
---

You are a senior developer planning a feature for the jobs hunt application. Always follow the rules in CLAUDE.md and develop based on the idea from feature-idea.md

User input: $ARGUMENTS

## Step 1 - Parse the arguments
From $ARGUMENTS extract:

1. 'step_number' - zero-padded to 2 digits: 2-02, 11-11
2. 'feature_title' - human readable title in Title Case
- Example: "Registration" or "Login and Logout"
3. 'feature_slug' - file sage slug
- lowercase, kebab-case
- Only a-z, 0-9 and -
- Maximum 40 characters
- Example: registration, login-logout

If you cannot infer these from $ARGUMENTS, ask the user to clarify before proceeding.

## Step 2 - Research the codebase
Read these files before writing the spec:
- CLAUDE.md - architecture, conventions, design points
- app/models.py - existing SQLAlchemy schema
- app/routes/ - existing route blueprints
- app/services/ - existing service layer
- .claude/ideation/feature-idea.md - the requirement to spec out
- All files in .claude/specs/ - avoid duplicating existing specs. If it is a duplicate, notify user "Spec already exists" with <name>

## Step 3 - Write the spec
Generate a spec document with this exact structure:

# Spec : <feature_title>

## Overview
One paragraph describing what this feature does and why it exists at this stage of the jobs-hunt roadmap.

## Depends on
which previous steps this feature requires to be complete.

## Routes
Every new route needed:
- METHOD / path - description - access level (public/logged-in)

If no new routes: state "No new routes"

## Database changes
Any new tables, columns or constrainsts needed.
Always verify against database/dp.py before writing this.
If none: state "No database changes"

## UI changes
Changes to `app/static/` files (index.html, app.js, style.css).
If none: state "No UI changes"

## Files to change
Every file that will be modified.

## Files to create
Every new file that will be created

## New dependencies
Any new pip packages. If None: state "No new dependencies"

## Rules for implementation
Specific constraints Claude must follow.
Always include:
- Use SQLAlchemy models; never write raw SQL
- Use CSS variables — never hardcode hex values
- Portal config belongs in config/portals.json, not in Python code
- Mock mode must remain functional after the change (APIFY_MOCK=true)
- No breaking changes to existing API response shapes

## Definition of done
A specific testable checklist. Each item must be something that can be verified by running the app

## Step 4 - Save the spec
Save to: .claude/specs/<step-number>-<feature_slug>.md

## Step 5 - Report to the user
Print a short summary in this exact format:

Spec file: .claude/specs/<step-number>-<feature_slug>.md

Title: <feature_title>

Then tell the user:
"Review the spec at .claude/specs/<step-number>-<feature_slug>.md
then enter Plan mode with Shift+Tab twice to begin implementation."

Do not print the full spec in chat unless explicitly asked.

## Step 6 - Archive the idea prompt
After saving the spec, copy `.claude/ideation/feature-idea.md` to `.claude/ideation/feature-idea-<feature_slug>.md`.
This preserves a record of the original requirement while keeping `feature-idea.md` free to be overwritten for the next feature.