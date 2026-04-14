import json
import queue
import threading
from flask import Blueprint, request, jsonify, Response, current_app, stream_with_context

from app import db
from app.models import Resume, Search, Job
from app.services.apify_service import run_search, load_portals_config
from app.services.scorer import tfidf_score, semantic_score_async

search_bp = Blueprint("search", __name__)

# In-memory SSE queues keyed by search_id
_sse_queues: dict[int, queue.Queue] = {}
_sse_lock = threading.Lock()


def _get_queue(search_id: int) -> queue.Queue:
    with _sse_lock:
        if search_id not in _sse_queues:
            _sse_queues[search_id] = queue.Queue()
        return _sse_queues[search_id]


def _push(search_id: int, event: str, data: dict):
    q = _get_queue(search_id)
    q.put({"event": event, "data": data})


@search_bp.route("/api/search", methods=["POST"])
def start_search():
    body = request.get_json(force=True) or {}

    roles = body.get("roles", [])
    if not roles:
        return jsonify({"error": "At least one role is required"}), 400

    resume = Resume.query.order_by(Resume.id.desc()).first()
    if not resume:
        return jsonify({"error": "Upload a resume first"}), 400

    portals = body.get("portals", [])
    if not portals:
        cfg = load_portals_config()
        portals = [k for k, v in cfg.items() if v.get("enabled", True)]

    search = Search(
        resume_id=resume.id,
        roles=json.dumps(roles),
        location=body.get("location"),
        country=body.get("country"),
        remote_only=1 if body.get("remote_only") else 0,
        experience=body.get("experience"),
        employment_type=json.dumps(body.get("employment_type", [])),
        date_posted=body.get("date_posted", "any"),
        salary_min=body.get("salary_min"),
        salary_currency=body.get("salary_currency", "USD"),
        max_results=body.get("max_results", current_app.config["MAX_RESULTS_DEFAULT"]),
        portals=json.dumps(portals),
        status="pending",
    )
    db.session.add(search)
    db.session.commit()

    search_id = search.id

    # Run search in background thread
    app = current_app._get_current_object()
    t = threading.Thread(
        target=_execute_search,
        args=(search_id, resume, portals, body, app),
        daemon=True,
    )
    t.start()

    return jsonify({"search_id": search_id}), 202


def _execute_search(search_id: int, resume, portals: list, params: dict, app):
    with app.app_context():
        search = db.session.get(Search, search_id)
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

        # Score and persist jobs
        resume_text = resume.raw_text
        for job_data in jobs:
            job_text = f"{job_data['title']} {job_data['description']}"
            score = tfidf_score(resume_text, job_text)

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
            )
            db.session.add(job)
            db.session.flush()  # get job.id before commit

            _push(search_id, "job_added", {
                "job_id": job.id,
                "title": job.title,
                "company": job.company,
                "fit_score": score,
            })

            # Fire async semantic scoring (sentence-transformers, free)
            semantic_score_async(job.id, resume_text, job_text, app)

        db.session.commit()
        search.status = "done"
        db.session.commit()

        _push(search_id, "status", {"status": "done", "total": len(jobs)})
        _push(search_id, "__done__", {})


@search_bp.route("/api/search/<int:search_id>/stream")
def stream(search_id):
    search = db.session.get(Search, search_id)
    if not search:
        return jsonify({"error": "Search not found"}), 404

    q = _get_queue(search_id)

    @stream_with_context
    def generate():
        while True:
            try:
                item = q.get(timeout=30)
            except queue.Empty:
                yield "event: ping\ndata: {}\n\n"
                continue

            event = item["event"]
            data = json.dumps(item["data"])
            yield f"event: {event}\ndata: {data}\n\n"

            if event == "__done__":
                break

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@search_bp.route("/api/search/<int:search_id>/results")
def results(search_id):
    search = db.session.get(Search, search_id)
    if not search:
        return jsonify({"error": "Search not found"}), 404

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 25, type=int)
    sort = request.args.get("sort", "fit_score")

    sort_col = Job.fit_score.desc()
    if sort == "company":
        sort_col = Job.company.asc()
    elif sort == "posted_at":
        sort_col = Job.posted_at.desc()

    pagination = (
        Job.query.filter_by(search_id=search_id)
        .order_by(sort_col)
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    return jsonify({
        "search": search.to_dict(),
        "jobs": [j.to_dict() for j in pagination.items],
        "total": pagination.total,
        "pages": pagination.pages,
        "page": page,
    })


@search_bp.route("/api/portals")
def list_portals():
    cfg = load_portals_config()
    return jsonify([
        {"key": k, "label": v.get("label", k), "enabled": v.get("enabled", True)}
        for k, v in cfg.items()
    ])
