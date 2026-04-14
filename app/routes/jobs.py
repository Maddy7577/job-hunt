from flask import Blueprint, jsonify, request

from app import db
from app.models import Job, Search

jobs_bp = Blueprint("jobs", __name__)


@jobs_bp.route("/api/jobs/<int:job_id>/save", methods=["POST"])
def toggle_save(job_id):
    job = db.session.get(Job, job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    job.saved = 0 if job.saved else 1
    db.session.commit()
    return jsonify({"saved": bool(job.saved)})


@jobs_bp.route("/api/saved")
def saved_jobs():
    jobs = Job.query.filter_by(saved=1).order_by(Job.fit_score.desc()).all()
    return jsonify([j.to_dict() for j in jobs])


@jobs_bp.route("/api/history")
def search_history():
    searches = Search.query.order_by(Search.id.desc()).limit(50).all()
    result = []
    for s in searches:
        d = s.to_dict()
        d["job_count"] = Job.query.filter_by(search_id=s.id).count()
        result.append(d)
    return jsonify(result)


@jobs_bp.route("/api/jobs/<int:job_id>/score")
def get_score(job_id):
    """Endpoint polled by the frontend for updated Claude score."""
    job = db.session.get(Job, job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify({
        "job_id": job_id,
        "fit_score": job.fit_score,
        "fit_rationale": job.fit_rationale,
    })
