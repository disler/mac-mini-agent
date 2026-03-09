import os

import httpx


def _headers() -> dict:
    key = os.environ.get("LISTEN_API_KEY", "")
    return {"X-API-Key": key} if key else {}


def start_job(url: str, prompt: str) -> dict:
    """POST to url/job with prompt, returns response dict."""
    response = httpx.post(f"{url}/job", json={"prompt": prompt}, headers=_headers())
    response.raise_for_status()
    return response.json()


def get_job(url: str, job_id: str) -> str:
    """GET url/job/{job_id}, returns YAML content."""
    response = httpx.get(f"{url}/job/{job_id}", headers=_headers())
    response.raise_for_status()
    return response.text


def list_jobs(url: str, archived: bool = False) -> str:
    """GET url/jobs, returns YAML content."""
    params = {"archived": "true"} if archived else {}
    response = httpx.get(f"{url}/jobs", params=params, headers=_headers())
    response.raise_for_status()
    return response.text


def clear_jobs(url: str) -> dict:
    """POST url/jobs/clear, returns response dict."""
    response = httpx.post(f"{url}/jobs/clear", headers=_headers())
    response.raise_for_status()
    return response.json()


def latest_jobs(url: str, n: int = 1) -> str:
    """GET the full details of the latest N jobs."""
    import yaml

    response = httpx.get(f"{url}/jobs", headers=_headers())
    response.raise_for_status()
    data = yaml.safe_load(response.text)
    jobs = data.get("jobs") or []
    # Jobs are sorted by file order; take the last N (most recent)
    latest = jobs[-n:] if n < len(jobs) else jobs
    latest.reverse()  # Most recent first

    parts = []
    for job in latest:
        job_id = job["id"]
        detail = httpx.get(f"{url}/job/{job_id}", headers=_headers())
        detail.raise_for_status()
        parts.append(detail.text)
    return "---\n".join(parts)


def stop_job(url: str, job_id: str) -> dict:
    """DELETE url/job/{job_id}, returns response dict."""
    response = httpx.delete(f"{url}/job/{job_id}", headers=_headers())
    response.raise_for_status()
    return response.json()
