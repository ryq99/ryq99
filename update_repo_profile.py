"""
Generate a Markdown table of your GitHub repos and inject it into a README.

Zero dependencies (stdlib only). Auth via the GITHUB_TOKEN env var.

Usage:
    GITHUB_TOKEN=ghp_xxx python update_repos.py \
        --user YOUR_USERNAME \
        --readme README.md \
        --visibility public          # public | private | all

The script replaces whatever sits between these two markers in the README:
    <!-- REPOS:START -->
    ... generated table ...
    <!-- REPOS:END -->
Add those two lines to your README once, wherever you want the table.
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error

API = "https://api.github.com"
START = "<!-- REPOS:START -->"
END = "<!-- REPOS:END -->"


def gh_get(url, token):
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "repo-table-generator",
    })
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read()), r.headers
    except urllib.error.HTTPError as e:
        sys.exit(f"GitHub API error {e.code}: {e.read().decode()[:300]}")


def fetch_repos(token, visibility):
    """Fetch repos owned by the authenticated user. Handles pagination."""
    repos, page = [], 1
    while True:
        # affiliation=owner => only repos you own (not org/collab noise)
        url = (f"{API}/user/repos?visibility={visibility}"
               f"&affiliation=owner&per_page=100&page={page}&sort=updated")
        batch, _ = gh_get(url, token)
        if not batch:
            break
        repos.extend(batch)
        page += 1
    return repos


def excluded(repo, names, topics, prefixes):
    if repo["name"] in names:
        return True
    if any(repo["name"].startswith(p) for p in prefixes):
        return True
    repo_topics = set(repo.get("topics", []))
    if repo_topics & topics:
        return True
    return False


def build_table(repos, show_visibility):
    header = "| Repo | Description | Language | ⭐ |"
    sep = "|------|-------------|----------|----|"
    if show_visibility:
        header = "| Repo | Description | Language | ⭐ | Visibility |"
        sep = "|------|-------------|----------|----|------------|"

    rows = []
    for r in sorted(repos, key=lambda x: (-x["stargazers_count"], x["name"].lower())):
        name = f"[{r['name']}]({r['html_url']})"
        desc = (r.get("description") or "").replace("|", "\\|").strip() or "—"
        lang = r.get("language") or "—"
        stars = r["stargazers_count"]
        cells = [name, desc, lang, str(stars)]
        if show_visibility:
            cells.append("🔒 Private" if r["private"] else "🌐 Public")
        rows.append("| " + " | ".join(cells) + " |")

    count_line = f"_{len(repos)} repositories_"
    return "\n".join([header, sep, *rows, "", count_line])


def inject(readme_path, table):
    with open(readme_path, "r", encoding="utf-8") as f:
        content = f.read()

    if START not in content or END not in content:
        sys.exit(f"Markers not found. Add these two lines to {readme_path}:\n"
                 f"{START}\n{END}")

    pre = content.split(START)[0]
    post = content.split(END)[1]
    new = f"{pre}{START}\n{table}\n{END}{post}"

    if new == content:
        print("No changes.")
        return False
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(new)
    print(f"Updated {readme_path}.")
    return True


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--user", required=True)
    p.add_argument("--readme", default="README.md")
    p.add_argument("--visibility", default="public",
                   choices=["public", "private", "all"])
    p.add_argument("--exclude-names", default="",
                   help="comma-separated repo names to skip")
    p.add_argument("--exclude-topics", default="work,sony,internal",
                   help="comma-separated topics; any match skips the repo")
    p.add_argument("--exclude-prefixes", default="",
                   help="comma-separated name prefixes to skip, e.g. 'wip-,tmp-'")
    p.add_argument("--show-visibility", action="store_true",
                   help="add a Public/Private column (use for private index)")
    args = p.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("Set GITHUB_TOKEN (a PAT with repo scope for private repos).")

    names = {s.strip() for s in args.exclude_names.split(",") if s.strip()}
    topics = {s.strip() for s in args.exclude_topics.split(",") if s.strip()}
    prefixes = [s.strip() for s in args.exclude_prefixes.split(",") if s.strip()]

    repos = fetch_repos(token, args.visibility)
    repos = [r for r in repos if not r.get("fork")
             and not excluded(r, names, topics, prefixes)]

    print(f"{len(repos)} repos after filtering "
          f"(excluded topics: {sorted(topics)}).")

    table = build_table(repos, args.show_visibility)
    inject(args.readme, table)


if __name__ == "__main__":
    main()
