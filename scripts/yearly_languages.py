#!/usr/bin/env python3
"""Render rolling-year languages from deduplicated authored public commits."""

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from xml.etree import ElementTree as ET


USER = "aidangarske"
LANGUAGES = {
    ".c": "C", ".h": "C", ".cc": "C++", ".cpp": "C++", ".cxx": "C++",
    ".hpp": "C++", ".hh": "C++", ".s": "Assembly", ".asm": "Assembly",
    ".rs": "Rust", ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript",
    ".mjs": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript",
    ".sh": "Shell", ".bash": "Shell", ".zsh": "Shell", ".java": "Java",
    ".cs": "C#", ".go": "Go", ".groovy": "Groovy", ".rb": "Ruby",
}
COLORS = ("#58a6ff", "#338fdd", "#2675bd", "#62b9e7", "#9ad8f5", "#1b5e95")
NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", NS)


def run(*args):
    return subprocess.run(args, capture_output=True, text=True, errors="replace", check=True,
                          timeout=600).stdout


def graphql(query):
    response = json.loads(run("gh", "api", "graphql", "-f", "query=" + query))
    if response.get("errors"):
        raise ValueError("GitHub could not collect the language source repositories")
    return response["data"]["user"]


def repositories(since, through):
    user = graphql('''query { user(login:"%s") {
      contributionsCollection(from:"%s",to:"%s") {
        commitContributionsByRepository(maxRepositories:100) {
          repository { nameWithOwner isPrivate }
        }
      }
    } }''' % (USER, since, through))
    result = {
        item["repository"]["nameWithOwner"]
        for item in user["contributionsCollection"]["commitContributionsByRepository"]
        if not item["repository"]["isPrivate"]
    }
    cursor = None
    while True:
        after = ",after:" + json.dumps(cursor) if cursor else ""
        owned = graphql('''query { user(login:"%s") {
          repositories(first:100,privacy:PUBLIC,ownerAffiliations:OWNER%s) {
            nodes { nameWithOwner pushedAt }
            pageInfo { hasNextPage endCursor }
          }
        } }''' % (USER, after))["repositories"]
        result.update(repo["nameWithOwner"] for repo in owned["nodes"]
                      if repo["pushedAt"] and repo["pushedAt"] >= since)
        if not owned["pageInfo"]["hasNextPage"]:
            return sorted(result)
        cursor = owned["pageInfo"]["endCursor"]


def is_author(name, email):
    name, email = name.casefold(), email.casefold()
    return (name == "aidan garske"
            or (name == "aidan" and email == "aidan@wolfssl.com")
            or "aidangarske@users.noreply.github.com" in email)


def authored_changes(repo, cache, since, through):
    directory = cache / repo.replace("/", "__")
    # Fetch every branch, including pending work in personal forks.
    if (directory / ".git").exists():
        run("git", "-C", str(directory), "fetch", "--quiet", "--prune", "origin")
    else:
        run("git", "clone", "--quiet", "--filter=blob:none", "--no-checkout",
            "--no-single-branch", "--no-tags",
            "https://github.com/" + repo + ".git", str(directory))
    return commit_changes(directory, since, through)


def commit_changes(directory, since, through):
    # Complete tree history keeps the oldest commit in the window from being
    # counted as an addition of every file in a shallow repository.
    log = run("git", "-C", str(directory), "log", "--all", "--no-merges",
              "--no-renames", "--name-only",
              "--format=COMMIT%x09%H%x09%an%x09%ae%x09%aI")
    start = datetime.fromisoformat(since.replace("Z", "+00:00"))
    end = datetime.fromisoformat(through.replace("Z", "+00:00"))
    commits = {}
    active = None
    for line in log.splitlines():
        if line.startswith("COMMIT\t"):
            _, sha, name, email, authored = line.split("\t", 4)
            authored_date = datetime.fromisoformat(authored.replace("Z", "+00:00"))
            active = sha if is_author(name, email) and start <= authored_date <= end else None
            if active:
                commits[active] = Counter()
        elif active and line:
            language = LANGUAGES.get(Path(line).suffix.lower())
            if language:
                commits[active][language] += 1
    return commits


def collect(cache, since, through):
    repos = repositories(since, through)
    commits = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = pool.map(lambda repo: authored_changes(repo, cache, since, through), repos)
        for index, changes in enumerate(results, 1):
            commits.update(changes)
            print("Collected %s/%s public repositories" % (index, len(repos)), flush=True)
    counts = Counter()
    for changes in commits.values():
        counts.update(changes)
    if not counts:
        raise ValueError("No authored source changes found; preserving the existing card")
    return {"since": since, "through": through, "repositories": len(repos),
            "authored_commits": len(commits), "source_file_changes": sum(counts.values()),
            "counts": dict(counts.most_common())}


def render(data, output):
    ordered = list(data["counts"].items())
    total = data["source_file_changes"]
    shown = ordered[:6]
    if len(ordered) > 6:
        shown = ordered[:5] + [("Other", sum(count for _, count in ordered[5:]))]
    height = 96 + 25 * ((len(shown) + 1) // 2)
    root = ET.Element("{%s}svg" % NS, {
        "width": "420", "height": str(height), "viewBox": "0 0 420 %s" % height,
        "role": "img", "aria-label": "Languages in Aidan's authored changes over the last year",
    })

    def add(tag, attrs=None, value=None):
        node = ET.SubElement(root, "{%s}%s" % (NS, tag), attrs or {})
        node.text = str(value) if value is not None else None
        return node

    def text(x, y, value, size=12, color="#c9d1d9", weight="400"):
        add("text", {"x": str(x), "y": str(y), "font-size": str(size), "fill": color,
                     "font-weight": weight, "font-family": "Segoe UI, Arial, sans-serif"}, value)

    add("title", value="Languages · last year")
    add("desc", value="Public authored source-file changes across all scanned branches; duplicate commit hashes count once.")
    add("metadata", {"id": "language-data"}, json.dumps(data, sort_keys=True))
    add("rect", {"width": "420", "height": str(height), "rx": "5", "fill": "#020c14"})
    text(25, 32, "Languages · last year", 18, "#58a6ff", "600")
    text(25, 51, "Authored source-file changes", 11, "#8b949e")
    x = 25.0
    for index, (_, count) in enumerate(shown):
        width = 370 * count / total
        add("rect", {"x": str(x), "y": "64", "width": str(width), "height": "8",
                     "fill": COLORS[index]})
        x += width
    for index, (name, count) in enumerate(shown):
        x = 25 + (index % 2) * 190
        y = 96 + (index // 2) * 25
        add("circle", {"cx": str(x + 4), "cy": str(y - 4), "r": "4", "fill": COLORS[index]})
        text(x + 14, y, "%s %.1f%%" % (name, 100 * count / total))
    text(25, height - 11, "%s — %s" % (data["since"][:10], data["through"][:10]), 10, "#8b949e")
    output.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(output, encoding="utf-8", xml_declaration=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("assets/top-languages.svg"))
    parser.add_argument("--cache-dir", type=Path)
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    since = (now - timedelta(days=365)).isoformat().replace("+00:00", "Z")
    through = now.isoformat().replace("+00:00", "Z")
    if args.cache_dir:
        args.cache_dir.mkdir(parents=True, exist_ok=True)
        data = collect(args.cache_dir, since, through)
    else:
        with TemporaryDirectory(prefix="yearly-languages-") as tmp:
            data = collect(Path(tmp), since, through)
    render(data, args.output)
    print("Rendered %s authored changes in %s unique commits" %
          (data["source_file_changes"], data["authored_commits"]))


if __name__ == "__main__":
    main()
