import os
import time
from flask import Blueprint, request, jsonify, current_app, send_file
import io

from app import db
from app.models import Resume
from app.services.resume_parser import extract_text

resume_bp = Blueprint("resume", __name__)

ALLOWED_MIMES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
}


@resume_bp.route("/api/resume", methods=["POST"])
def upload_resume():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Empty filename"}), 400

    mime = f.mimetype
    # Accept pdf/docx by extension if browser sends wrong MIME
    if f.filename.lower().endswith(".pdf"):
        mime = "application/pdf"
    elif f.filename.lower().endswith(".docx"):
        mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    if mime not in ALLOWED_MIMES:
        return jsonify({"error": "Only PDF and DOCX files are accepted"}), 400

    file_data = f.read()
    try:
        raw_text = extract_text(file_data, mime)
    except Exception as exc:
        return jsonify({"error": f"Could not parse file: {exc}"}), 422

    upload_folder = current_app.config["UPLOAD_FOLDER"]
    timestamp = int(time.time())
    safe_name = f"{timestamp}_{f.filename}"
    file_path = os.path.join(upload_folder, safe_name)
    with open(file_path, "wb") as out:
        out.write(file_data)

    resume = Resume(
        filename=f.filename,
        file_data=file_data,
        file_path=file_path,
        mime_type=mime,
        raw_text=raw_text,
    )
    db.session.add(resume)
    db.session.commit()

    return jsonify(resume.to_dict()), 201


@resume_bp.route("/api/resume", methods=["GET"])
def get_resume():
    resume = Resume.query.order_by(Resume.id.desc()).first()
    if not resume:
        return jsonify({"error": "No resume uploaded"}), 404
    return jsonify(resume.to_dict())


@resume_bp.route("/api/resume/download", methods=["GET"])
def download_resume():
    resume = Resume.query.order_by(Resume.id.desc()).first()
    if not resume:
        return jsonify({"error": "No resume uploaded"}), 404

    return send_file(
        io.BytesIO(resume.file_data),
        mimetype=resume.mime_type,
        as_attachment=True,
        download_name=resume.filename,
    )
