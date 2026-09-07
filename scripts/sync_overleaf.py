#!/usr/bin/env python3
"""
Auto-discovers your public GitHub repos and syncs any new ones directly into your
live Overleaf resume - no manual project list to maintain.

For each public, non-fork repo under config.yaml's github_username that isn't already
present (tracked via a "% repo:owner/name" comment inside the markers), fetches the
repo's README/description, drafts a matching LaTeX entry via the configured AI provider
(or uses a manual override from overrides.yaml), and appends it inside the
AUTO-PROJECTS-START/END markers of your actual main .tex file. Then commits and pushes
straight back to the Overleaf project via its git bridge.

Requires env vars: OVERLEAF_PROJECT_ID, OVERLEAF_GIT_TOKEN, GITHUB_TOKEN,
and one of ANTHROPIC_API_KEY / OPENAI_API_KEY / GOOGLE_API_KEY (matching config.yaml's ai_provider)
"""
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_github import get_repo_info, list_public_repos
from lib_ai_entry import draft_latex_entry

ROOT = Path(__file__).resolve().parent.parent
CLONE_DIR = ROOT / "overleaf-project"


def load_config():
    config = yaml.safe_load((ROOT / "config.yaml").read_text())
    overrides_path = ROOT / "overrides.yaml"
    overrides = {}
    if overrides_path.exists():
        overrides = (yaml.safe_load(overrides_path.read_text()) or {}).get("overrides", {}) or {}
    return config, overrides


def this_pipeline_repo() -> str | None:
    """The 'owner/name' of the repo this Action is running in, so we never sync ourselves."""
    return os.environ.get("GITHUB_REPOSITORY")  # provided automatically by GitHub Actions


def clone_overleaf_project():
    project_id = os.environ["OVERLEAF_PROJECT_ID"]
    token = os.environ["OVERLEAF_GIT_TOKEN"]
    url = f"https://git:{token}@git.overleaf.com/{project_id}"

    if CLONE_DIR.exists():
        subprocess.run(["rm", "-rf", str(CLONE_DIR)], check=True)
    subprocess.run(["git", "clone", url, str(CLONE_DIR)], check=True, capture_output=True, text=True)


def read_main_tex(main_tex_file: str) -> str:
    path = CLONE_DIR / main_tex_file
    if not path.exists():
        raise FileNotFoundError(
            f"'{main_tex_file}' not found in the Overleaf project. "
            f"Check config.yaml's main_tex_file setting."
        )
    return path.read_text()


def extract_marked_block(content: str, start_marker: str, end_marker: str):
    """Returns (before, block, after) split on the marker lines."""
    start_idx = content.find(start_marker)
    end_idx = content.find(end_marker)
    if start_idx == -1 or end_idx == -1:
        raise ValueError(
            f"Could not find both markers ({start_marker!r} / {end_marker!r}) in the main tex file. "
            f"Add them once around your existing Projects section — see config.yaml for an example."
        )
    block_start = start_idx + len(start_marker)
    block = content[block_start:end_idx]
    before = content[: start_idx + len(start_marker)]
    after = content[end_idx:]
    return before, block, after


def already_synced_repos(block: str) -> set:
    return set(re.findall(r"%\s*repo:(\S+)", block))


def discover_new_repos(config: dict, synced: set) -> list[str]:
    username = config["github_username"]
    exclude_names = set(config.get("exclude_repos", []) or [])
    self_repo = this_pipeline_repo()

    all_repos = list_public_repos(username)
    new_repos = []
    for repo in all_repos:
        name = repo.split("/", 1)[1]
        if repo in synced:
            continue
        if name in exclude_names:
            continue
        if self_repo and repo.lower() == self_repo.lower():
            continue
        new_repos.append(repo)
    return new_repos


def main():
    config, overrides = load_config()
    main_tex_file = config["main_tex_file"]
    start_marker = config["start_marker"]
    end_marker = config["end_marker"]
    ai_provider = config.get("ai_provider", "google")
    ai_model = config.get("ai_model", "gemini-3-flash")

    print("Cloning Overleaf project...")
    clone_overleaf_project()

    content = read_main_tex(main_tex_file)
    before, block, after = extract_marked_block(content, start_marker, end_marker)
    synced = already_synced_repos(block)

    print(f"Listing public repos for {config['github_username']}...")
    new_repos = discover_new_repos(config, synced)

    if not new_repos:
        print("No new repos to sync.")
        return

    new_entries = []
    for repo in new_repos:
        name = repo.split("/", 1)[1]
        print(f"New project detected: {repo}")
        print(f"  Fetching GitHub info...")
        repo_info = get_repo_info(repo)
        print(f"  Drafting matching LaTeX entry via {ai_provider}/{ai_model}...")
        current_style = block + "\n" + "\n".join(new_entries)
        override_bullets = (overrides.get(name) or {}).get("bullets")
        entry = draft_latex_entry(
            repo_info,
            current_style,
            override_bullets=override_bullets,
            provider=ai_provider,
            model=ai_model,
        )
        new_entries.append(entry)

    updated_block = block.rstrip() + "\n\n" + "\n\n".join(new_entries) + "\n"
    updated_content = before + updated_block + after

    (CLONE_DIR / main_tex_file).write_text(updated_content)

    print(f"Added {len(new_entries)} new entr{'y' if len(new_entries) == 1 else 'ies'}. Pushing to Overleaf...")
    subprocess.run(["git", "config", "user.name", "resume-bot"], cwd=CLONE_DIR, check=True)
    subprocess.run(["git", "config", "user.email", "actions@github.com"], cwd=CLONE_DIR, check=True)
    subprocess.run(["git", "add", main_tex_file], cwd=CLONE_DIR, check=True)
    subprocess.run(
        ["git", "commit", "-m", f"Auto-add {len(new_entries)} project entr{'y' if len(new_entries)==1 else 'ies'}"],
        cwd=CLONE_DIR, check=True,
    )
    subprocess.run(["git", "push"], cwd=CLONE_DIR, check=True)
    print("Done.")


if __name__ == "__main__":
    main()
