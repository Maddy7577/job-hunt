import os
import threading
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# ── Sentence-transformers model (loaded once, lazily) ─────────────────
_st_model = None
_st_lock = threading.Lock()


def _get_st_model():
    """Load the sentence-transformers model on first use."""
    global _st_model
    if _st_model is not None:
        return _st_model
    with _st_lock:
        if _st_model is None:
            try:
                from sentence_transformers import SentenceTransformer
                _st_model = SentenceTransformer("all-MiniLM-L6-v2")
            except Exception:
                _st_model = None   # fall back to TF-IDF only
    return _st_model


# ── Fast TF-IDF score (used immediately when job arrives) ─────────────

def tfidf_score(resume_text: str, job_text: str) -> int:
    """Return a 0–100 TF-IDF cosine similarity score."""
    if not resume_text or not job_text:
        return 0
    try:
        vec = TfidfVectorizer(stop_words="english")
        tfidf = vec.fit_transform([resume_text, job_text])
        score = cosine_similarity(tfidf[0:1], tfidf[1:2])[0][0]
        return min(100, int(round(score * 100)))
    except Exception:
        return 0


# ── Semantic score (replaces Claude — free, runs locally) ─────────────

def semantic_score_async(job_id: int, resume_text: str, job_text: str, app):
    """
    Fire a background thread that computes a semantic similarity score
    using sentence-transformers (all-MiniLM-L6-v2) and generates a
    keyword-based rationale. Updates the DB when done.

    This replaces the Claude API call to keep scoring free.
    To switch back to Claude, see the commented-out block below.
    """
    t = threading.Thread(
        target=_run_semantic_score,
        args=(job_id, resume_text, job_text, app),
        daemon=True,
    )
    t.start()


def _run_semantic_score(job_id: int, resume_text: str, job_text: str, app):
    try:
        score, rationale = _compute_semantic(resume_text, job_text)

        with app.app_context():
            from app.models import Job
            from app import db

            job = db.session.get(Job, job_id)
            if job:
                job.fit_score = score
                job.fit_rationale = rationale
                db.session.commit()
    except Exception:
        pass


def _compute_semantic(resume_text: str, job_text: str) -> tuple[int, str]:
    """
    Returns (score 0-100, one-sentence rationale).
    Uses sentence-transformers if available, else falls back to TF-IDF.
    """
    model = _get_st_model()

    if model is not None:
        from sklearn.metrics.pairwise import cosine_similarity as cos_sim
        import numpy as np

        resume_emb = model.encode([resume_text[:2000]], convert_to_numpy=True)
        job_emb = model.encode([job_text[:2000]], convert_to_numpy=True)
        raw = float(cos_sim(resume_emb, job_emb)[0][0])
        # Stretch the [0,1] range: scores cluster in 0.2–0.8, rescale to 0–100
        score = min(100, int(round(max(0.0, (raw - 0.1) / 0.7) * 100)))
    else:
        score = tfidf_score(resume_text, job_text)

    rationale = _keyword_rationale(resume_text, job_text, score)
    return score, rationale


def _keyword_rationale(resume_text: str, job_text: str, score: int) -> str:
    """
    Generate a one-sentence fit rationale by comparing keyword overlap.
    Completely free — no API calls.
    """
    import re

    def keywords(text):
        words = re.findall(r"\b[a-zA-Z][a-zA-Z0-9+#._-]{2,}\b", text.lower())
        stopwords = {
            "the", "and", "for", "with", "that", "this", "have", "will", "are",
            "you", "our", "your", "their", "from", "they", "been", "has", "was",
            "its", "all", "can", "not", "but", "more", "also", "any", "new",
        }
        return {w for w in words if w not in stopwords}

    resume_kw = keywords(resume_text[:3000])
    job_kw = keywords(job_text[:3000])
    matched = resume_kw & job_kw

    # Pick the most "interesting" matched keywords (longer = more specific)
    top = sorted(matched, key=len, reverse=True)[:5]

    if score >= 75:
        if top:
            return f"Strong match — resume and role share key skills: {', '.join(top[:3])}."
        return "Strong overall alignment between resume and job requirements."
    elif score >= 50:
        if top:
            return f"Partial match — some overlap in {', '.join(top[:3])}, but gaps remain."
        return "Moderate fit — some relevant experience, but not a direct match."
    else:
        if top:
            return f"Weak match — limited overlap; only {', '.join(top[:2])} align."
        return "Low fit — resume skills don't closely match this role's requirements."


# ── Claude API scoring (commented out — re-enable when paid key is ready) ──
#
# def _run_claude_score(job_id: int, resume_text: str, job_text: str, app):
#     api_key = os.getenv("ANTHROPIC_API_KEY")
#     if not api_key:
#         return
#     try:
#         import anthropic, json, re
#         client = anthropic.Anthropic(api_key=api_key)
#         prompt = (
#             "You are a professional recruiter. Given the resume and job description below, "
#             "reply with ONLY a JSON object with two keys:\n"
#             '- "score": an integer 0-100 representing how well the candidate fits the role\n'
#             '- "rationale": one sentence explaining the main strength or gap\n\n'
#             f"RESUME:\n{resume_text[:3000]}\n\nJOB DESCRIPTION:\n{job_text[:3000]}"
#         )
#         message = client.messages.create(
#             model="claude-haiku-4-5-20251001",
#             max_tokens=150,
#             messages=[{"role": "user", "content": prompt}],
#         )
#         raw = message.content[0].text.strip()
#         match = re.search(r"\{.*\}", raw, re.DOTALL)
#         if not match:
#             return
#         data = json.loads(match.group())
#         score = int(data.get("score", 0))
#         rationale = str(data.get("rationale", ""))
#         with app.app_context():
#             from app.models import Job
#             from app import db
#             job = db.session.get(Job, job_id)
#             if job:
#                 job.fit_score = score
#                 job.fit_rationale = rationale
#                 db.session.commit()
#     except Exception:
#         pass
