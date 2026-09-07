"""Fetches repo description, topics, languages, and README text from the GitHub API."""
import base64
import os

import requests

GITHUB_API = "https://api.github.com"


def _headers():
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def get_repo_info(repo: str) -> dict:
    """repo: 'owner/name' string. Returns description, topics, languages, README text, url."""
    headers = _headers()

    r = requests.get(f"{GITHUB_API}/repos/{repo}", headers=headers, timeout=15)
    r.raise_for_status()
    data = r.json()

    topics_r = requests.get(f"{GITHUB_API}/repos/{repo}/topics", headers=headers, timeout=15)
    topics = topics_r.json().get("names", []) if topics_r.ok else []

    lang_r = requests.get(f"{GITHUB_API}/repos/{repo}/languages", headers=headers, timeout=15)
    languages = list(lang_r.json().keys()) if lang_r.ok else []

    readme_text = ""
    readme_r = requests.get(f"{GITHUB_API}/repos/{repo}/readme", headers=headers, timeout=15)
    if readme_r.ok:
        content = readme_r.json().get("content", "")
        try:
            readme_text = base64.b64decode(content).decode("utf-8", errors="ignore")
        except Exception:
            readme_text = ""

    return {
        "repo": repo,
        "name": data.get("name"),
        "description": data.get("description") or "",
        "topics": topics,
        "languages": languages,
        "readme": readme_text,
        "html_url": data.get("html_url"),
    }


def list_public_repos(username: str) -> list[str]:
    """Returns 'owner/name' strings for every public, non-fork repo owned by this user."""
    headers = _headers()
    repos = []
    page = 1
    while True:
        r = requests.get(
            f"{GITHUB_API}/users/{username}/repos",
            headers=headers,
            params={"type": "owner", "per_page": 100, "page": page},
            timeout=15,
        )
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        for repo in batch:
            if repo.get("fork"):
                continue
            if repo.get("private"):
                continue
            repos.append(repo["full_name"])
        if len(batch) < 100:
            break
        page += 1
    return repos


if __name__ == "__main__":
    import json
    import sys

    info = get_repo_info(sys.argv[1])
    print(json.dumps({k: (v[:200] if k == "readme" else v) for k, v in info.items()}, indent=2))
