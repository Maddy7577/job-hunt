"""
digest_service.py — AutoHunt Mail Digest

Pure Python, no Flask imports at module level.
Orchestrates: Gemini ATS tailoring → fpdf2 PDF → Gmail SMTP send.
"""

import logging
import os
import re
import smtplib
import time
from datetime import datetime
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid

log = logging.getLogger(__name__)

# ── Gemini ATS system prompt ──────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are an elite resume writer and ATS optimisation expert with 15 years of experience \
helping candidates land interviews at top companies. You deeply understand how ATS systems \
parse, score, and rank resumes — and how recruiters read them.

Your task is to produce a tailored, ATS-optimised resume for the provided job description, \
using ONLY the experience, skills, titles, tools, and dates present in the original resume. \
Never fabricate anything.

=== ATS OPTIMISATION STRATEGY ===
Before rewriting, mentally perform these steps:
1. Extract must-have keywords from the JD (required skills, tools, methodologies, job title variants).
2. Extract nice-to-have keywords (preferred skills, domain knowledge).
3. Identify the seniority signals (years of experience required, leadership scope).
4. Map each keyword to real evidence in the original resume.
5. Weave matched keywords naturally into the summary and bullet points — exact phrase matches \
score higher in ATS than synonyms.

=== REWRITING RULES ===
1. Never invent tools, titles, companies, metrics, dates, or achievements not in the original resume.
2. Rephrase existing bullet points using the JD's exact action verbs and terminology where truthful.
3. Quantify achievements wherever numbers exist in the original (team size, % improvement, project count).
4. Surface the most JD-relevant bullet points first within each role.
5. Write a punchy 3-sentence summary: (a) seniority + job title from JD, (b) top 3 matched competencies, \
(c) one concrete career achievement.
6. Reorder skills: JD-matching skills first, then supporting skills, then general skills.
7. Use plain ASCII only — no Unicode bullets, em-dashes, smart quotes, or special characters.

=== OUTPUT FORMAT — follow this EXACTLY ===
Line 1: Candidate full name only (no label)
Line 2: email | phone | city, country | LinkedIn (use only what is in the original resume)
[blank line]
SUMMARY
[3 sentences, no bullet points]
[blank line]
EXPERIENCE
[blank line]
[Job Title] | [Company Name] | [Mon Year - Mon Year or Present]
- [Achievement or responsibility — start with strong action verb]
- [Achievement or responsibility]
[blank line]
[Previous Job Title] | [Previous Company] | [Mon Year - Mon Year]
- [Achievement]
[blank line]
SKILLS
[blank line]
[Category label]: [skill1, skill2, skill3]
[blank line]
EDUCATION
[blank line]
[Degree] | [Institution] | [Year]
[blank line]
CERTIFICATIONS
[blank line]
[Certification Name] | [Issuing Body] | [Year]

Rules for the output format:
- Omit any section (CERTIFICATIONS, EDUCATION etc.) not present in the original resume.
- Section headers must be ALL-CAPS on their own line with no punctuation.
- Every experience bullet must start with "- " (hyphen space).
- Do not include any commentary, notes, labels like "Note:", or markdown formatting.
- Return ONLY the resume. Nothing else.\
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sanitise_filename(s: str) -> str:
    """Strip characters unsafe for file names, preserving word separators."""
    return re.sub(r"[^a-zA-Z0-9 _-]", "_", s)


# ── Core functions ────────────────────────────────────────────────────────────

def tailor_resume(resume_text: str, job_description: str) -> str:
    """
    Call Gemini 2.0 Flash Lite (free tier) to rewrite resume_text for job_description.
    Raises RuntimeError if GEMINI_API_KEY is not set.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not configured")

    from google import genai                    # lazy import
    from google.genai import types

    client = genai.Client(api_key=api_key)
    user_message = (
        f"=== ORIGINAL RESUME ===\n{resume_text}\n\n"
        f"=== JOB DESCRIPTION ===\n{job_description}"
    )
    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=user_message,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
        ),
    )
    return response.text


def _safe(text: str) -> str:
    """Encode to latin-1, replacing unmappable chars."""
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _is_section_header(line: str) -> bool:
    """True if the line is an ALLCAPS section header (e.g. EXPERIENCE, SKILLS)."""
    stripped = line.strip()
    return (
        len(stripped) >= 3
        and stripped.replace(" ", "").isupper()
        and stripped.replace(" ", "").isalpha()
    )


def _is_role_line(line: str) -> bool:
    """True if line looks like 'Job Title | Company | Dates'."""
    parts = line.split("|")
    return len(parts) >= 2 and any(
        c.isdigit() for c in parts[-1]
    )


def _is_bullet(line: str) -> bool:
    return line.startswith("- ") or line.startswith("* ")


def build_pdf(tailored_text: str) -> bytes:
    """
    Render a professionally formatted single-column resume PDF from the
    structured text produced by tailor_resume().

    Layout:
      - Line 1  → candidate name (large, bold, centred)
      - Line 2  → contact info (small, centred)
      - ALLCAPS → section header + full-width underline rule
      - Role lines (Title | Company | Dates) → bold title, italic company/dates
      - "- bullet" lines → indented bullet points with • symbol
      - Category: skills lines → bold category label + regular skills
      - Everything else → regular body text
    """
    from fpdf import FPDF

    # ── Layout constants ──────────────────────────────────────────────────────
    L, R, T, B   = 18, 18, 18, 18          # margins mm
    BODY_SIZE    = 10
    NAME_SIZE    = 18
    CONTACT_SIZE = 9
    HEADER_SIZE  = 11
    ROLE_SIZE    = 10.5
    BULLET_INDENT = 5
    LINE_H       = 5.2                      # body line height mm
    RULE_COLOR   = (60, 60, 60)

    pdf = FPDF(format="A4")
    pdf.set_margins(left=L, top=T, right=R)
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=B)
    W = pdf.w - L - R                       # usable width

    lines = [ln.rstrip() for ln in tailored_text.splitlines()]

    # ── Identify header block (name + contact = first two non-blank lines) ────
    non_blank = [ln for ln in lines if ln.strip()]
    name_line    = _safe(non_blank[0].strip()) if len(non_blank) > 0 else ""
    contact_line = _safe(non_blank[1].strip()) if len(non_blank) > 1 else ""
    # Skip the contact line if it looks like a section header
    if _is_section_header(contact_line):
        contact_line = ""

    # ── Render name ───────────────────────────────────────────────────────────
    pdf.set_font("Helvetica", style="B", size=NAME_SIZE)
    pdf.cell(W, 10, name_line, ln=True, align="C")

    # ── Render contact line ───────────────────────────────────────────────────
    if contact_line:
        pdf.set_font("Helvetica", size=CONTACT_SIZE)
        pdf.set_text_color(80, 80, 80)
        pdf.multi_cell(W, 5, contact_line, align="C")
        pdf.set_text_color(0, 0, 0)

    pdf.ln(3)

    # ── Render body (skip the first two non-blank lines already rendered) ─────
    skip_count = 0
    header_done = False

    for raw in lines:
        line = raw.strip()

        # Skip the name and contact lines at the top
        if not header_done:
            if line == non_blank[0].strip() and skip_count == 0:
                skip_count = 1
                continue
            if contact_line and line == non_blank[1].strip() and skip_count == 1:
                skip_count = 2
                continue
            if skip_count >= (2 if contact_line else 1):
                header_done = True
            elif not line:
                continue

        if not line:
            pdf.ln(2)
            continue

        safe = _safe(line)

        # Section header
        if _is_section_header(safe):
            pdf.ln(3)
            pdf.set_font("Helvetica", style="B", size=HEADER_SIZE)
            pdf.set_text_color(*RULE_COLOR)
            pdf.cell(W, 6, safe.upper(), ln=True)
            # Underline rule
            x = pdf.get_x()
            y = pdf.get_y()
            pdf.set_draw_color(*RULE_COLOR)
            pdf.set_line_width(0.4)
            pdf.line(L, y, L + W, y)
            pdf.ln(2)
            pdf.set_text_color(0, 0, 0)
            continue

        # Role line: Title | Company | Dates
        if _is_role_line(safe):
            pdf.ln(1)
            parts = [p.strip() for p in safe.split("|")]
            role    = _safe(parts[0])
            rest    = " | ".join(_safe(p) for p in parts[1:])

            # Role title in bold
            pdf.set_font("Helvetica", style="B", size=ROLE_SIZE)
            role_w = pdf.get_string_width(role) + 2
            pdf.cell(role_w, LINE_H + 0.8, role)

            # Company + dates in italic, right-aligned
            pdf.set_font("Helvetica", style="I", size=BODY_SIZE - 0.5)
            rest_w = W - role_w
            pdf.cell(rest_w, LINE_H + 0.8, " | " + rest, ln=True, align="R")
            continue

        # Bullet point
        if _is_bullet(safe):
            text = safe[2:].strip()
            pdf.set_font("Helvetica", size=BODY_SIZE)
            pdf.set_x(L + BULLET_INDENT)
            bullet_w = W - BULLET_INDENT
            pdf.multi_cell(bullet_w, LINE_H, "- " + text)
            continue

        # Skills category line: "Category: skill1, skill2"
        if ":" in safe and not safe.startswith("-"):
            colon = safe.index(":")
            category = _safe(safe[:colon].strip())
            skills   = _safe(safe[colon + 1:].strip())
            pdf.set_font("Helvetica", style="B", size=BODY_SIZE)
            cat_w = pdf.get_string_width(category + ": ") + 1
            pdf.cell(cat_w, LINE_H, category + ": ")
            pdf.set_font("Helvetica", size=BODY_SIZE)
            pdf.multi_cell(W - cat_w, LINE_H, skills)
            continue

        # Regular body text
        pdf.set_font("Helvetica", size=BODY_SIZE)
        pdf.multi_cell(W, LINE_H, safe)

    return bytes(pdf.output())


def send_job_email(job, pdf_bytes: bytes, pdf_filename: str) -> None:
    """
    Send one email for `job` with the tailored PDF resume attached.
    Raises RuntimeError if required env vars are not set.
    """
    gmail_address = os.getenv("GMAIL_ADDRESS", "")
    app_password = os.getenv("GMAIL_APP_PASSWORD", "")
    notify_email = os.getenv("NOTIFY_EMAIL") or gmail_address

    if not app_password:
        raise RuntimeError("GMAIL_APP_PASSWORD not configured")
    if not gmail_address:
        raise RuntimeError("GMAIL_ADDRESS not configured")

    fit = job.fit_score
    fit_pct = f"{int(fit * 100)}%" if fit is not None else "N/A"
    jd_excerpt = (job.description or "")[:300].strip()
    if len(job.description or "") > 300:
        jd_excerpt += "…"

    # Include company in subject to make each email unique (prevents Gmail threading)
    subject = f"AutoHunt: {job.title} at {job.company}"

    html_body = f"""\
<html><body style="font-family:Arial,sans-serif;font-size:14px;color:#222;">
<h2 style="margin-bottom:4px">{job.title}</h2>
<p style="margin:0;color:#555">
  <strong>{job.company}</strong> &nbsp;|&nbsp;
  {job.portal} &nbsp;|&nbsp;
  {job.location or 'Location N/A'} &nbsp;|&nbsp;
  {job.experience or ''} &nbsp;|&nbsp;
  Fit score: <strong>{fit_pct}</strong>
</p>
<hr style="margin:12px 0">
<p style="white-space:pre-wrap;font-size:13px;color:#444">{jd_excerpt}</p>
<hr style="margin:12px 0">
<p>
  <a href="{job.url}" style="background:#1a73e8;color:#fff;padding:10px 20px;
     border-radius:4px;text-decoration:none;font-weight:bold">Apply →</a>
</p>
<p style="font-size:11px;color:#999;margin-top:24px">
  Tailored resume attached as <em>{pdf_filename}</em>. Sent by AutoHunt.
</p>
</body></html>"""

    msg = MIMEMultipart("mixed")
    msg["From"] = f"AutoHunt <{gmail_address}>"
    msg["To"] = notify_email
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain="autohunt.mail")   # unique per email → no threading
    msg["X-Mailer"] = "AutoHunt Job Digest"
    msg.attach(MIMEText(html_body, "html"))

    attachment = MIMEBase("application", "octet-stream")
    attachment.set_payload(pdf_bytes)
    encoders.encode_base64(attachment)
    attachment.add_header(
        "Content-Disposition", "attachment", filename=pdf_filename
    )
    msg.attach(attachment)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_address, app_password)
        server.send_message(msg)


def send_digest(search_id: int, app_ctx, push_fn) -> None:
    """
    Main digest loop. Iterates over unsent jobs for `search_id`, tailors the
    resume, builds a PDF, sends an email, and marks each job as sent.

    `push_fn(search_id, event_name, data_dict)` is injected by the caller to
    avoid a circular import with the route module.
    """
    with app_ctx.app_context():
        from app import db
        from app.models import Job, JobDigestStatus, Resume

        # Only process jobs that have no digest status row or are still "New"
        notified_ids = {
            row.job_id
            for row in JobDigestStatus.query
            .filter_by(status="Notified")
            .all()
        }
        jobs = (
            Job.query
            .filter_by(search_id=search_id, autohunt_filtered=0)
            .filter(Job.id.notin_(notified_ids))
            .all()
        )
        resume = Resume.query.order_by(Resume.id.desc()).first()

        total = len(jobs)
        sent = 0
        errors = 0

        for i, job in enumerate(jobs):
            try:
                tailored = tailor_resume(resume.raw_text if resume else "", job.description or "")
                pdf_bytes = build_pdf(tailored)
                company_safe = _sanitise_filename(job.company or "Company")
                title_safe = _sanitise_filename(job.title or "Role")
                filename = f"Resume_{title_safe}_{company_safe}.pdf"
                send_job_email(job, pdf_bytes, filename)

                # Upsert digest status → Notified
                ds = db.session.get(JobDigestStatus, job.id)
                if ds is None:
                    ds = JobDigestStatus(job_id=job.id, status="Notified",
                                         notified_at=datetime.utcnow())
                    db.session.add(ds)
                else:
                    ds.status = "Notified"
                    ds.notified_at = datetime.utcnow()
                db.session.commit()
                sent += 1
            except Exception as exc:
                log.error("Digest failed for job %s (%s @ %s): %s",
                          job.id, job.title, job.company, exc)
                errors += 1
                push_fn(search_id, "digest_progress", {
                    "sent": sent,
                    "total": total,
                    "current_company": job.company,
                    "current_title": job.title,
                    "error": str(exc),
                })
                if i < total - 1:
                    time.sleep(4)
                continue

            push_fn(search_id, "digest_progress", {
                "sent": sent,
                "total": total,
                "current_company": job.company,
                "current_title": job.title,
            })

            # Respect Gemini free-tier rate limit (15 RPM → 4 s gap)
            if i < total - 1:
                time.sleep(4)

        push_fn(search_id, "digest_done", {"sent": sent, "total": total, "errors": errors})
        push_fn(search_id, "__digest_done__", {})
