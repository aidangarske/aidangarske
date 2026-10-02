#!/usr/bin/env python3
"""Render yearly language activity and career source-line additions."""

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import os
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
COLORS = {
    "C": "#a8b9cc", "C++": "#f34b7d", "C#": "#b56bc3",
    "Shell": "#89e051", "Rust": "#dea584", "TypeScript": "#3178c6",
    "Python": "#3572a5", "JavaScript": "#f1e05a", "Assembly": "#c59b55",
    "Go": "#00add8", "Java": "#e79432", "Groovy": "#4298b8", "Ruby": "#cc342d",
}
NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", NS)


def run(*args, input=None, env=None):
    return subprocess.run(args, input=input, env=env, capture_output=True, text=True, errors="replace", check=True,
                          timeout=600).stdout


def graphql(query):
    response = json.loads(run("gh", "api", "graphql", "-f", "query=" + query))
    if response.get("errors"):
        raise ValueError("GitHub could not collect the language source repositories")
    return response["data"]["user"]


def repositories(since, through):
    years = graphql('query { user(login:"%s") { contributionsCollection { contributionYears } } }'
                    % USER)["contributionsCollection"]["contributionYears"]
    sections = []
    for year in years:
        end = min(through, "%s-12-31T23:59:59Z" % year)
        sections.append('''y%s: contributionsCollection(from:"%s-01-01T00:00:00Z",to:"%s") {
          commitContributionsByRepository(maxRepositories:100) {
            repository { nameWithOwner isPrivate }
          }
        }''' % (year, year, end))
    history = graphql('query { user(login:"%s") { %s } }' % (USER, " ".join(sections)))
    result = set()
    for collection in history.values():
        contributed = collection["commitContributionsByRepository"]
        if len(contributed) == 100:
            raise ValueError("GitHub's repository discovery limit was reached")
        result.update(item["repository"]["nameWithOwner"] for item in contributed
                      if not item["repository"]["isPrivate"])
    cursor = None
    while True:
        after = ",after:" + json.dumps(cursor) if cursor else ""
        owned = graphql('''query { user(login:"%s") {
          repositories(first:100,privacy:PUBLIC,ownerAffiliations:OWNER%s) {
            nodes { nameWithOwner }
            pageInfo { hasNextPage endCursor }
          }
        } }''' % (USER, after))["repositories"]
        result.update(repo["nameWithOwner"] for repo in owned["nodes"])
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
    args = ["git", "-C", str(directory), "log", "--all", "--full-history", "--no-merges", "--regexp-ignore-case",
            "--author=^Aidan Garske <", "--author=^Aidan <aidan@wolfssl.com>",
            "--author=aidangarske@users.noreply.github.com"]
    # Filter by author before asking Git to compute file diffs. A path-limited
    # history walk can needlessly compare every upstream commit's trees.
    # Fetch changed blobs together instead of one network request per diff.
    raw = run(*args, "--raw", "--no-abbrev", "--no-renames", "--format=")
    objects = set()
    for line in raw.splitlines():
        if line.startswith(":"):
            fields = line.split("\t", 1)[0].split()
            for mode, oid in zip((fields[0][1:], fields[1]), fields[2:4]):
                # Gitlinks point into a separate submodule repository.
                if mode != "160000" and set(oid) != {"0"}:
                    objects.add(oid)
    if objects:
        checked = run("git", "-C", str(directory), "cat-file", "--batch-check",
                      input="\n".join(sorted(objects)) + "\n",
                      env=dict(os.environ, GIT_NO_LAZY_FETCH="1"))
        missing = [line.split()[0] for line in checked.splitlines() if line.endswith(" missing")]
        for offset in range(0, len(missing), 2048):
            run("git", "-C", str(directory), "-c", "fetch.negotiationAlgorithm=noop",
                "fetch", "--quiet", "--no-tags", "--no-write-fetch-head", "--filter=blob:none",
                "--stdin", "origin", input="\n".join(missing[offset:offset + 2048]) + "\n")
    log = run(*args, "--numstat", "-z", "--find-renames", "--format=%x1e%H%x00%an%x00%ae%x00%aI%x00")
    end = datetime.fromisoformat(through.replace("Z", "+00:00"))
    commits = {}
    active = None
    tokens = iter(log.split("\0"))
    for token in tokens:
        token = token.lstrip("\n")
        if token.startswith("\x1e"):
            sha = token[1:]
            name, email, authored = next(tokens), next(tokens), next(tokens)
            authored_date = datetime.fromisoformat(authored.replace("Z", "+00:00"))
            active = sha if is_author(name, email) and authored_date <= end else None
            if active:
                commits[active] = {"authored": authored, "files": Counter(),
                                   "added": Counter(), "deleted": Counter()}
        elif token:
            added, deleted, path = token.split("\t", 2)
            if not path:
                next(tokens)  # Old path of a renamed file.
                path = next(tokens)
            language = LANGUAGES.get(Path(path).suffix.lower())
            if not active:
                continue
            if language:
                commits[active]["files"][language] += 1
                if added != "-":  # Git marks binary diffs with a dash.
                    commits[active]["added"][language] += int(added)
                    commits[active]["deleted"][language] += int(deleted)
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
    career_added = Counter()
    career_deleted = Counter()
    year_added = Counter()
    year_commits = 0
    start = datetime.fromisoformat(since.replace("Z", "+00:00"))
    for changes in commits.values():
        career_added.update(changes["added"])
        career_deleted.update(changes["deleted"])
        if datetime.fromisoformat(changes["authored"].replace("Z", "+00:00")) >= start:
            counts.update(changes["files"])
            year_added.update(changes["added"])
            year_commits += 1
    if not counts:
        raise ValueError("No authored source changes found; preserving the existing card")
    return {"since": since, "through": through, "repositories": len(repos),
            "authored_commits": year_commits, "source_file_changes": sum(counts.values()),
            "counts": dict(counts.most_common()), "career_commits": len(commits),
            "career_loc_added": sum(career_added.values()),
            "career_loc_deleted": sum(career_deleted.values()),
            "career_added": dict(career_added.most_common()),
            "career_deleted": dict(career_deleted.most_common()),
            "year_added": dict(year_added.most_common()),
            "loc_method": "Public Git source-line additions, including comments and blank lines; non-merge authored commits; exact SHA duplicates counted once; renames detected."}


def render(data, output):
    names = set(data["counts"]) | set(data["career_added"])
    shown = sorted(((name, data["counts"].get(name, 0)) for name in names),
                   key=lambda item: (item[1], data["career_added"].get(item[0], 0)), reverse=True)
    total = data["source_file_changes"]
    height = 135 + 28 * ((len(shown) + 1) // 2)
    root = ET.Element("{%s}svg" % NS, {
        "width": "520", "height": str(height), "viewBox": "0 0 520 %s" % height,
        "role": "img", "aria-label": "Languages in Aidan's authored changes over the last year",
    })

    def add(tag, attrs=None, value=None):
        node = ET.SubElement(root, "{%s}%s" % (NS, tag), attrs or {})
        node.text = str(value) if value is not None else None
        return node

    def text(x, y, value, size=14, color="#c9d1d9", weight="400"):
        add("text", {"x": str(x), "y": str(y), "font-size": str(size), "fill": color,
                     "font-weight": weight, "font-family": "Segoe UI, Arial, sans-serif"}, value)

    add("title", value="Languages · last year")
    add("desc", value=data["loc_method"])
    add("metadata", {"id": "language-data"}, json.dumps(data, sort_keys=True))
    add("rect", {"width": "520", "height": str(height), "rx": "5", "fill": "#020c14"})
    text(25, 32, "Languages · last year", 20, "#58a6ff", "600")
    text(25, 54, "Career LOC added: %s" % f"{data['career_loc_added']:,}", 15, "#c9d1d9", "600")
    text(25, 73, "%s removed · public Git history" % f"{data['career_loc_deleted']:,}", 12, "#8b949e")
    text(25, 93, "Last-year activity % · career LOC added", 12, "#8b949e")
    x = 25.0
    for name, count in shown:
        width = 470 * count / total
        add("rect", {"x": str(x), "y": "105", "width": str(width), "height": "8",
                     "fill": COLORS.get(name, "#8b949e")})
        x += width
    for index, (name, count) in enumerate(shown):
        x = 25 + (index % 2) * 238
        y = 137 + (index // 2) * 28
        add("circle", {"cx": str(x + 4), "cy": str(y - 4), "r": "4", "fill": COLORS.get(name, "#8b949e")})
        percentage = 100 * count / total
        value = "<0.1%" if 0 < percentage < 0.1 else "%.1f%%" % percentage
        loc = data["career_added"].get(name, 0)
        amount = f"{loc:,}"
        text(x + 14, y, "%s %s · %s LOC" % (name, value, amount), 13)
    text(25, height - 11, "%s — %s" % (data["since"][:10], data["through"][:10]), 11, "#8b949e")
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
    print("Rendered %s yearly authored changes and %s career source lines added" %
          (data["source_file_changes"], data["career_loc_added"]))


if __name__ == "__main__":
    main()
