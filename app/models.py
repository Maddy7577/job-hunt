from datetime import datetime
from app import db



class Resume(db.Model):
    __tablename__ = "resume"

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.Text, nullable=False)
    file_data = db.Column(db.LargeBinary, nullable=False)
    file_path = db.Column(db.Text, nullable=False)
    mime_type = db.Column(db.Text, nullable=False)
    raw_text = db.Column(db.Text, nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "filename": self.filename,
            "file_path": self.file_path,
            "mime_type": self.mime_type,
            "uploaded_at": self.uploaded_at.isoformat(),
        }


class Search(db.Model):
    __tablename__ = "search"

    id = db.Column(db.Integer, primary_key=True)
    resume_id = db.Column(db.Integer, db.ForeignKey("resume.id"))
    roles = db.Column(db.Text, nullable=False)          # JSON array
    location = db.Column(db.Text)
    country = db.Column(db.Text)
    remote_only = db.Column(db.Integer, default=0)
    experience = db.Column(db.Text)
    employment_type = db.Column(db.Text)                # JSON array
    date_posted = db.Column(db.Text)
    salary_min = db.Column(db.Integer)
    salary_currency = db.Column(db.Text, default="USD")
    max_results = db.Column(db.Integer, default=50)
    portals = db.Column(db.Text, nullable=False)        # JSON array
    status = db.Column(db.Text, default="pending")      # pending|running|done|error
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    jobs = db.relationship("Job", backref="search", lazy=True)

    def to_dict(self):
        import json
        return {
            "id": self.id,
            "resume_id": self.resume_id,
            "roles": json.loads(self.roles),
            "location": self.location,
            "country": self.country,
            "remote_only": bool(self.remote_only),
            "experience": self.experience,
            "employment_type": json.loads(self.employment_type) if self.employment_type else [],
            "date_posted": self.date_posted,
            "salary_min": self.salary_min,
            "salary_currency": self.salary_currency,
            "max_results": self.max_results,
            "portals": json.loads(self.portals),
            "status": self.status,
            "created_at": self.created_at.isoformat(),
        }


class Job(db.Model):
    __tablename__ = "job"

    id = db.Column(db.Integer, primary_key=True)
    search_id = db.Column(db.Integer, db.ForeignKey("search.id"), nullable=False)
    portal = db.Column(db.Text, nullable=False)
    external_id = db.Column(db.Text)
    title = db.Column(db.Text, nullable=False)
    company = db.Column(db.Text, nullable=False)
    location = db.Column(db.Text)
    experience = db.Column(db.Text)
    employment_type = db.Column(db.Text)
    description = db.Column(db.Text)
    salary_text = db.Column(db.Text)
    url = db.Column(db.Text, nullable=False)
    posted_at = db.Column(db.DateTime)
    fit_score = db.Column(db.Float)
    fit_rationale = db.Column(db.Text)
    saved = db.Column(db.Integer, default=0)
    dedup_key           = db.Column(db.Text)
    autohunt_filtered   = db.Column(db.Integer, default=0)

    __table_args__ = (
        db.Index("idx_job_search", "search_id"),
        db.Index("idx_job_score", "search_id", "fit_score"),
        db.Index("idx_job_dedup", "search_id", "dedup_key"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "search_id": self.search_id,
            "portal": self.portal,
            "external_id": self.external_id,
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "experience": self.experience,
            "employment_type": self.employment_type,
            "description": self.description,
            "salary_text": self.salary_text,
            "url": self.url,
            "posted_at": self.posted_at.isoformat() if self.posted_at else None,
            "fit_score": self.fit_score,
            "fit_rationale": self.fit_rationale,
            "saved": bool(self.saved),
            "dedup_key": self.dedup_key,
            "autohunt_filtered": bool(self.autohunt_filtered),
        }


class AutoHuntProfile(db.Model):
    __tablename__ = "autohunt_profile"

    id         = db.Column(db.Integer, primary_key=True)
    skills     = db.Column(db.Text, nullable=False)          # JSON array
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class JobDigestStatus(db.Model):
    """Tracks email notification status per job. One row per job."""
    __tablename__ = "job_digest_status"

    job_id      = db.Column(db.Integer, db.ForeignKey("job.id"), primary_key=True)
    status      = db.Column(db.Text, nullable=False, default="New")   # "New" | "Notified"
    notified_at = db.Column(db.DateTime, nullable=True)

    job = db.relationship("Job", backref=db.backref("digest_status", uselist=False))

    def to_dict(self):
        return {
            "job_id": self.job_id,
            "status": self.status,
            "notified_at": self.notified_at.isoformat() if self.notified_at else None,
        }
