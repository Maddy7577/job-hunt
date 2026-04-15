import json
import os
import queue as _queue
import threading
from datetime import datetime

from flask import Blueprint, request, jsonify, current_app, Response, stream_with_context

from app import db
from app.models import AutoHuntProfile, Resume, Search, Job, JobDigestStatus
from app.services.apify_service import run_search, load_portals_config
from app.services.scorer import tfidf_score, semantic_score_async
from app.services.autohunt_filter import should_include
from app.routes.search import _push

autohunt_bp = Blueprint("autohunt", __name__)

# ── Digest SSE queues (separate from hunt SSE in search.py) ──────────────────
_digest_queues: dict[int, _queue.Queue] = {}
_digest_lock = threading.Lock()


def _digest_get_queue(search_id: int) -> _queue.Queue:
    with _digest_lock:
        if search_id not in _digest_queues:
            _digest_queues[search_id] = _queue.Queue()
        return _digest_queues[search_id]


def _digest_push(search_id: int, event: str, data: dict) -> None:
    _digest_get_queue(search_id).put({"event": event, "data": data})

# ── Fixed profile constants ───────────────────────────────────────────────────
_AUTOHUNT_LOCATION  = "Pune, India"
_AUTOHUNT_COUNTRY   = "IN"
_AUTOHUNT_EXPERIENCE = "lead"        # 11+ years → lead level
_AUTOHUNT_MAX       = 50
_DEFAULT_SKILLS     = ["Test Manager", "Worksoft Certify", "Agentic AI", "Claude"]


def _get_or_create_profile() -> AutoHuntProfile:
    profile = db.session.get(AutoHuntProfile, 1)
    if not profile:
        profile = AutoHuntProfile(id=1, skills=json.dumps(_DEFAULT_SKILLS))
        db.session.add(profile)
        db.session.commit()
    return profile


# ── GET /api/autohunt/profile ─────────────────────────────────────────────────
@autohunt_bp.route("/api/autohunt/profile", methods=["GET"])
def get_profile():
    profile = _get_or_create_profile()
    return jsonify({"skills": json.loads(profile.skills)})


# ── PUT /api/autohunt/profile ─────────────────────────────────────────────────
@autohunt_bp.route("/api/autohunt/profile", methods=["PUT"])
def update_profile():
    body = request.get_json(force=True) or {}
    skills = body.get("skills", [])
    if not isinstance(skills, list):
        return jsonify({"error": "skills must be a list"}), 400

    cleaned = [str(s).strip() for s in skills if str(s).strip()]
    profile = _get_or_create_profile()
    profile.skills = json.dumps(cleaned)
    profile.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"skills": json.loads(profile.skills)})


# ── POST /api/autohunt/hunt ───────────────────────────────────────────────────
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
        remote_only=0,
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
    }

    t = threading.Thread(
        target=_execute_autohunt,
        args=(search_id, resume.id, portals, params, app),
        daemon=True,
    )
    t.start()

    return jsonify({"search_id": search_id}), 202


# ── Background worker ─────────────────────────────────────────────────────────
def _execute_autohunt(search_id: int, resume_id: int, portals: list, params: dict, app):
    with app.app_context():
        search = db.session.get(Search, search_id)
        resume = db.session.get(Resume, resume_id)
        search.status = "running"
        db.session.commit()

        _push(search_id, "status", {"status": "running", "portals": portals})

        def progress_cb(portal_key, status, count):
            _push(search_id, "portal_done", {
                "portal": portal_key,
                "status": status,
                "count": count,
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

        try:
            for job_data in jobs:
                filtered = not should_include(job_data.get("description", ""))
                job_text = f"{job_data['title']} {job_data['description']}"
                score = None if filtered else tfidf_score(resume_text, job_text)

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
                        "job_id": job.id,
                        "title": job.title,
                        "company": job.company,
                        "fit_score": score,
                    })
                    semantic_score_async(job.id, resume_text, job_text, app)

            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            search.status = "error"
            db.session.commit()
            _push(search_id, "error", {"message": f"Failed to save jobs: {exc}"})
            _push(search_id, "__done__", {})
            return

        search.status = "done"
        db.session.commit()

        _push(search_id, "status", {"status": "done", "total": kept})
        _push(search_id, "__done__", {})


# ── POST /api/autohunt/<search_id>/digest ─────────────────────────────────────
@autohunt_bp.route("/api/autohunt/<int:search_id>/digest", methods=["POST"])
def start_digest(search_id):
    if not os.getenv("GEMINI_API_KEY"):
        return jsonify({"error": "GEMINI_API_KEY not configured"}), 503
    if not os.getenv("GMAIL_APP_PASSWORD"):
        return jsonify({"error": "GMAIL_APP_PASSWORD not configured"}), 503

    notified_ids = [
        row.job_id for row in
        JobDigestStatus.query.filter_by(status="Notified").all()
    ]
    base_q = Job.query.filter_by(search_id=search_id, autohunt_filtered=0)
    if notified_ids:
        base_q = base_q.filter(Job.id.notin_(notified_ids))
    count = base_q.count()
    if count == 0:
        return jsonify({"status": "nothing_to_send", "total": 0}), 200

    _digest_get_queue(search_id)          # pre-create queue before thread starts
    app = current_app._get_current_object()
    threading.Thread(
        target=_run_digest, args=(search_id, app), daemon=True
    ).start()
    return jsonify({"status": "started", "total": count}), 202


def _run_digest(search_id: int, app) -> None:
    from app.services.digest_service import send_digest
    send_digest(search_id, app, _digest_push)


# ── GET /api/autohunt/<search_id>/digest/stream ───────────────────────────────
@autohunt_bp.route("/api/autohunt/<int:search_id>/digest/stream")
def digest_stream(search_id):
    q = _digest_get_queue(search_id)

    @stream_with_context
    def generate():
        while True:
            try:
                item = q.get(timeout=30)
            except _queue.Empty:
                yield "event: ping\ndata: {}\n\n"
                continue
            event = item["event"]
            yield f"event: {event}\ndata: {json.dumps(item['data'])}\n\n"
            if event == "__digest_done__":
                break

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── GET /api/autohunt/email-config ────────────────────────────────────────────
@autohunt_bp.route("/api/autohunt/email-config")
def email_config():
    gmail = os.getenv("GMAIL_ADDRESS", "")
    notify = os.getenv("NOTIFY_EMAIL") or gmail
    configured = bool(
        gmail
        and os.getenv("GMAIL_APP_PASSWORD")
        and os.getenv("GEMINI_API_KEY")
    )
    # GMAIL_APP_PASSWORD is intentionally not returned
    return jsonify({
        "gmail_address": gmail,
        "notify_email": notify,
        "configured": configured,
    })
