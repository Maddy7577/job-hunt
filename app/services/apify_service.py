import os
import json
import hashlib
import random
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
PORTALS_CONFIG_PATH = os.path.join(BASE_DIR, "config", "portals.json")

# ── Mock mode ──────────────────────────────────────────────────────────
# Set to False (or set env var APIFY_MOCK=false) once you have an
# Apify API token and want to run real actor calls.
MOCK_MODE = os.getenv("APIFY_MOCK", "true").lower() != "false"


def load_portals_config() -> dict:
    with open(PORTALS_CONFIG_PATH) as f:
        return json.load(f)


def build_apify_input(portal_key: str, portal_cfg: dict, params: dict) -> dict:
    """Translate canonical search params into the actor's expected input format."""
    param_map = portal_cfg.get("param_map", {})

    experience_raw = params.get("experience", "")
    experience_mapped = param_map.get("experience", {}).get(experience_raw, experience_raw)

    date_raw = params.get("date_posted", "any")
    date_mapped = param_map.get("date_posted", {}).get(date_raw, "")

    roles = params.get("roles", [])
    keywords = " ".join(roles) if roles else ""

    payload = {
        "position": keywords,
        "keywords": keywords,
        "location": params.get("location", ""),
        "country": params.get("country", ""),
        "remote": params.get("remote_only", False),
        "experienceLevel": experience_mapped,
        "datePosted": date_mapped,
        "maxItems": params.get("max_results", 50),
    }

    if params.get("salary_min"):
        payload["salaryMin"] = params["salary_min"]
        payload["salaryCurrency"] = params.get("salary_currency", "USD")

    emp_types = params.get("employment_type", [])
    if emp_types:
        payload["employmentType"] = ",".join(emp_types)

    return payload


# ── Mock data ──────────────────────────────────────────────────────────

_MOCK_COMPANIES = [
    "Stripe", "Airbnb", "Notion", "Figma", "Vercel", "Shopify", "Cloudflare",
    "HashiCorp", "Databricks", "Snowflake", "MongoDB", "Confluent", "Grafana Labs",
    "PlanetScale", "Supabase", "Linear", "Retool", "Amplitude", "Mixpanel", "Segment",
    "Twilio", "SendGrid", "Plaid", "Brex", "Ramp", "Scale AI", "Hugging Face",
    "Weights & Biases", "LangChain", "Cohere",
]

_MOCK_ROLE_TEMPLATES = {
    "default": [
        "{role}",
        "Senior {role}",
        "Staff {role}",
        "Principal {role}",
        "Lead {role}",
        "{role} II",
        "{role} III",
        "Junior {role}",
    ]
}

_MOCK_LOCATIONS = [
    "San Francisco, CA", "New York, NY", "Seattle, WA", "Austin, TX",
    "Boston, MA", "Chicago, IL", "Remote", "London, UK", "Toronto, ON",
    "Berlin, Germany", "Amsterdam, Netherlands", "Singapore",
]

_MOCK_SALARY = [
    "$120,000 – $150,000", "$140,000 – $180,000", "$160,000 – $200,000",
    "$100,000 – $130,000", "$180,000 – $240,000", "Competitive",
    "£80,000 – £110,000", "€70,000 – €95,000", "",
]

_MOCK_EXP_LEVELS = ["entry", "mid", "senior", "lead", "executive"]

_MOCK_EMP_TYPES = ["Full-time", "Contract", "Full-time", "Full-time", "Contract"]

_MOCK_JD_SNIPPETS = [
    (
        "We are looking for a {role} to join our platform team. You will design and build "
        "scalable distributed systems, own critical infrastructure components, and work closely "
        "with product and design teams. Strong experience with Python or Go, PostgreSQL, and "
        "cloud platforms (AWS/GCP) is required. Experience with Kubernetes and Terraform is a plus."
    ),
    (
        "As a {role} you will be responsible for developing and maintaining our core API services. "
        "You'll collaborate with a cross-functional team to deliver high-quality software. We use "
        "React, TypeScript, Node.js, and GraphQL on the stack. You'll own features end-to-end "
        "from design through deployment."
    ),
    (
        "Join our ML platform team as a {role}. You will build tooling to accelerate model "
        "training and deployment pipelines. Familiarity with PyTorch, MLflow, and distributed "
        "training is essential. Experience with data pipelines using Spark or Flink is highly valued."
    ),
    (
        "We're hiring a {role} to help scale our data infrastructure. Responsibilities include "
        "designing data models, building ETL pipelines, and enabling analytics across the org. "
        "Proficiency in SQL, dbt, and experience with Snowflake or BigQuery required."
    ),
    (
        "As a {role} on our security team, you will conduct threat modelling, code reviews, and "
        "penetration testing. You will develop security tooling, respond to incidents, and work "
        "with engineering teams to embed security best practices into the SDLC."
    ),
    (
        "Looking for a {role} to own mobile app development across iOS and Android. You'll work "
        "with React Native and native modules, collaborate on design systems, and own releases. "
        "Experience with CI/CD, app store processes, and performance profiling required."
    ),
    (
        "We need a {role} to drive our DevOps and platform strategy. You will build and maintain "
        "CI/CD pipelines, manage our Kubernetes clusters, and own our observability stack "
        "(Prometheus, Grafana, OpenTelemetry). Strong IaC skills with Terraform are required."
    ),
    (
        "As a {role} at our fintech startup you will build payment processing systems that handle "
        "billions in transactions. Strong understanding of financial systems, PCI compliance, and "
        "idempotent API design required. Experience with event-driven architecture is a plus."
    ),
]


def _mock_run_actor(portal_key: str, payload: dict, max_items: int) -> list:
    """Generate realistic-looking fake job listings for development."""
    roles_kw = payload.get("keywords") or payload.get("position") or "Software Engineer"
    role_parts = roles_kw.split()
    base_role = " ".join(role_parts) if role_parts else "Software Engineer"

    count = random.randint(max(3, max_items // 6), max(8, max_items // 3))
    items = []

    for _ in range(count):
        company = random.choice(_MOCK_COMPANIES)
        template = random.choice(_MOCK_ROLE_TEMPLATES["default"])
        title = template.format(role=base_role)
        location = random.choice(_MOCK_LOCATIONS)
        salary = random.choice(_MOCK_SALARY)
        exp = random.choice(_MOCK_EXP_LEVELS)
        emp = random.choice(_MOCK_EMP_TYPES)
        jd = random.choice(_MOCK_JD_SNIPPETS).format(role=base_role)
        days_ago = random.randint(0, 14)
        posted = (datetime.utcnow() - timedelta(days=days_ago)).isoformat()
        job_id = hashlib.md5(f"{company}{title}{location}{portal_key}".encode()).hexdigest()[:12]

        items.append({
            "id": job_id,
            "title": title,
            "company": company,
            "location": location,
            "salary": salary,
            "experienceLevel": exp,
            "employmentType": emp,
            "description": jd,
            "url": f"https://{portal_key}.example.com/jobs/{job_id}",
            "postedAt": posted,
        })

    return items


# ── Real Apify call (uncomment when APIFY_API_TOKEN is set) ───────────

def run_actor(actor_id: str, payload: dict) -> list:
    """Call an Apify actor and return its dataset items."""
    if MOCK_MODE:
        portal_key = payload.get("_portal_key", "portal")
        max_items = int(payload.get("maxItems", 50))
        return _mock_run_actor(portal_key, payload, max_items)

    # ── Real Apify call — enable by setting APIFY_MOCK=false in .env ──
    # api_token = os.getenv("APIFY_API_TOKEN")
    # if not api_token:
    #     raise RuntimeError("APIFY_API_TOKEN not set")
    #
    # from apify_client import ApifyClient
    # client = ApifyClient(api_token)
    # run = client.actor(actor_id).call(run_input=payload)
    # dataset_id = run.get("defaultDatasetId")
    # if not dataset_id:
    #     return []
    # return list(client.dataset(dataset_id).iterate_items())

    raise RuntimeError("APIFY_MOCK is false but real Apify call is commented out. "
                       "Uncomment the block above and set APIFY_API_TOKEN.")


# ── Normaliser ────────────────────────────────────────────────────────

def normalise_item(raw: dict, portal_key: str) -> dict | None:
    """Map a raw Apify item to a canonical JobRecord dict."""
    title = (
        raw.get("title") or raw.get("jobTitle") or raw.get("position") or raw.get("name") or ""
    )
    company = (
        raw.get("company") or raw.get("companyName") or raw.get("employer") or raw.get("organization") or ""
    )
    url = (
        raw.get("url") or raw.get("jobUrl") or raw.get("applyUrl") or raw.get("link") or ""
    )
    if not title or not company or not url:
        return None

    location = raw.get("location") or raw.get("jobLocation") or raw.get("city") or ""
    description = (
        raw.get("description") or raw.get("jobDescription")
        or raw.get("descriptionHtml") or raw.get("details") or ""
    )
    salary_text = raw.get("salary") or raw.get("salaryText") or raw.get("compensation") or ""
    experience = raw.get("experienceLevel") or raw.get("experience") or raw.get("seniority") or ""
    employment_type = raw.get("employmentType") or raw.get("jobType") or raw.get("type") or ""
    external_id = str(raw.get("id") or raw.get("jobId") or raw.get("externalId") or "")

    posted_at = None
    for key in ("postedAt", "datePosted", "posted", "createdAt", "date"):
        val = raw.get(key)
        if val:
            try:
                if isinstance(val, (int, float)):
                    posted_at = datetime.utcfromtimestamp(val / 1000 if val > 1e10 else val)
                else:
                    posted_at = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
            except Exception:
                pass
            if posted_at:
                break

    dedup_key = hashlib.md5(
        f"{company.lower().strip()}|{title.lower().strip()}|{location.lower().strip()}".encode()
    ).hexdigest()

    return {
        "portal": portal_key,
        "external_id": external_id,
        "title": title.strip(),
        "company": company.strip(),
        "location": location.strip(),
        "experience": str(experience),
        "employment_type": str(employment_type),
        "description": str(description),
        "salary_text": str(salary_text),
        "url": url.strip(),
        "posted_at": posted_at,
        "dedup_key": dedup_key,
    }


# ── Fan-out runner ────────────────────────────────────────────────────

def run_search(search_params: dict, selected_portals: list, progress_cb=None) -> list:
    """
    Fan out actor runs in parallel across selected portals.
    progress_cb(portal_key, status, count) called after each portal completes.
    Returns a deduplicated list of normalised JobRecord dicts.
    """
    portals_cfg = load_portals_config()

    def run_one(portal_key):
        cfg = portals_cfg.get(portal_key)
        if not cfg:
            return portal_key, [], "unknown_portal"
        payload = build_apify_input(portal_key, cfg, search_params)
        payload["_portal_key"] = portal_key   # passed through to mock
        try:
            raw_items = run_actor(cfg["actor_id"], payload)
            jobs = [j for raw in raw_items if (j := normalise_item(raw, portal_key))]
            return portal_key, jobs, "done"
        except Exception as exc:
            return portal_key, [], f"error: {exc}"

    max_workers = min(len(selected_portals), 8)
    all_jobs = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(run_one, p): p for p in selected_portals}
        for future in as_completed(futures):
            portal_key, jobs, status = future.result()
            if progress_cb:
                progress_cb(portal_key, status, len(jobs))
            all_jobs.extend(jobs)

    # Deduplicate: keep first occurrence
    deduped = {}
    for job in all_jobs:
        if job["dedup_key"] not in deduped:
            deduped[job["dedup_key"]] = job

    return list(deduped.values())
