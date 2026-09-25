#!/usr/bin/env python3
"""Collect public GitHub metrics and languages from Aidan's authored source changes."""

import argparse
from collections import Counter
from datetime import date, timedelta
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory


USER = "aidangarske"
LANGUAGES = {
    ".c": "C", ".h": "C", ".cc": "C++", ".cpp": "C++", ".cxx": "C++",
    ".hpp": "C++", ".hh": "C++", ".s": "Assembly", ".asm": "Assembly",
    ".rs": "Rust", ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript",
    ".mjs": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript",
    ".sh": "Shell", ".bash": "Shell", ".zsh": "Shell", ".java": "Java",
    ".cs": "C#", ".go": "Go", ".groovy": "Groovy", ".rb": "Ruby",
}
QUERY = '''query {
  user(login:"aidangarske") {
    name login createdAt followers { totalCount }
    repositories(first:100, privacy:PUBLIC, ownerAffiliations:OWNER) {
      totalCount nodes { stargazerCount }
    }
    contributionsCollection {
      totalCommitContributions
      commitContributionsByRepository(maxRepositories:100) {
        repository { nameWithOwner isPrivate }
        contributions(first:1) { totalCount }
      }
    }
  }
  prs: search(query:"author:aidangarske type:pr", type:ISSUE, first:1) { issueCount }
  issues: search(query:"author:aidangarske type:issue", type:ISSUE, first:1) { issueCount }
  reviews: search(query:"reviewed-by:aidangarske type:pr", type:ISSUE, first:1) { issueCount }
  commented: search(query:"commenter:aidangarske", type:ISSUE, first:1) { issueCount }
}'''


def run(*args):
    return subprocess.run(args, text=True, capture_output=True, check=True).stdout


def is_aidan(name, email):
    name, email = name.casefold(), email.casefold()
    return name == "aidan garske" or (name == "aidan" and email == "aidan@wolfssl.com") or "aidangarske@users.noreply.github.com" in email


def repo_languages(directory, since):
    output = run("git", "-C", str(directory), "log", "--since=" + since,
                 "--no-merges", "--name-only", "--format=COMMIT%x09%an%x09%ae")
    active = False
    commits = 0
    counts = Counter()
    for line in output.splitlines():
        if line.startswith("COMMIT\t"):
            _, name, email = line.split("\t", 2)
            active = is_aidan(name, email)
            commits += int(active)
        elif active and line:
            extension = ".s" if line.endswith(".S") else Path(line).suffix.lower()
            language = LANGUAGES.get(extension)
            if language:
                counts[language] += 1
    return commits, counts


def collect(cache, since):
    response = json.loads(run("gh", "api", "graphql", "-f", "query=" + QUERY))
    if response.get("errors"):
        raise ValueError(response["errors"])
    payload = response["data"]
    user = payload["user"]
    contributed = [
        {"name": item["repository"]["nameWithOwner"],
         "commits": item["contributions"]["totalCount"]}
        for item in user["contributionsCollection"]["commitContributionsByRepository"]
        if not item["repository"]["isPrivate"]
    ]
    contributed.sort(key=lambda item: item["commits"], reverse=True)
    selected = contributed[:12]
    languages = Counter()
    authored_commits = 0
    for item in selected:
        repo = item["name"]
        directory = cache / repo.replace("/", "__")
        if not (directory / ".git").exists():
            run("git", "clone", "--quiet", "--filter=blob:none", "--no-checkout",
                "--single-branch", "--shallow-since=" + since,
                "https://github.com/" + repo + ".git", str(directory))
        commits, counts = repo_languages(directory, since)
        authored_commits += commits
        languages.update(counts)
        print("%s: %s authored commits" % (repo, commits), flush=True)
    return {
        "as_of": date.today().isoformat(),
        "login": user["login"],
        "name": user["name"],
        "joined": user["createdAt"][:10],
        "followers": user["followers"]["totalCount"],
        "public_repos": user["repositories"]["totalCount"],
        "owned_repo_stars": sum(repo["stargazerCount"] for repo in user["repositories"]["nodes"]),
        "commits_last_year": user["contributionsCollection"]["totalCommitContributions"],
        "repos_with_commits_last_year": len(contributed),
        "prs_opened": payload["prs"]["issueCount"],
        "prs_reviewed": payload["reviews"]["issueCount"],
        "issues_opened": payload["issues"]["issueCount"],
        "threads_commented": payload["commented"]["issueCount"],
        "rank": "A++",  # Preserved from the existing GitHub score card.
        "top_repos": selected[:3],
        "languages": {
            "since": since,
            "repositories": len(selected),
            "authored_commits": authored_commits,
            "source_file_changes": sum(languages.values()),
            "counts": dict(languages.most_common()),
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("data/profile-metrics.json"))
    parser.add_argument("--cache-dir", type=Path)
    args = parser.parse_args()
    since = (date.today() - timedelta(days=365)).isoformat()
    if args.cache_dir:
        data = collect(args.cache_dir, since)
    else:
        with TemporaryDirectory(prefix="profile-metrics-") as tmp:
            data = collect(Path(tmp), since)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, indent=2) + "\n")


if __name__ == "__main__":
    main()
