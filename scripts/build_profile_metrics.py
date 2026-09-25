#!/usr/bin/env python3
"""Render one compact blue profile panel from collected GitHub data and the 3D calendar."""

import argparse
import copy
import json
from datetime import date
from pathlib import Path
from xml.etree import ElementTree as ET


NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", NS)
BLUE = "#58a6ff"
PALE = "#d5e2f0"
MUTED = "#8b949e"
SHADES = ("#58a6ff", "#338fdd", "#2675bd", "#62b9e7", "#9ad8f5", "#1b5e95")


def tag(name):
    return "{%s}%s" % (NS, name)


def add(parent, name, attrs=None, value=None):
    node = ET.SubElement(parent, tag(name), attrs or {})
    if value is not None:
        node.text = str(value)
    return node


def text(parent, x, y, value, size=10, color=MUTED, weight="normal", anchor=None):
    attrs = {
        "x": str(x), "y": str(y), "fill": color,
        "font-family": "Arial, Helvetica, sans-serif",
        "font-size": str(size), "font-weight": weight,
    }
    if anchor:
        attrs["text-anchor"] = anchor
    return add(parent, "text", attrs, value)


def graph_data(path):
    root = ET.parse(path).getroot()
    graph = next((child for child in root if child.tag == tag("g") and len(child) > 300), None)
    if graph is None:
        raise ValueError("3D contribution graph group was not found")
    metadata = root.find(tag("metadata"))
    if metadata is None or metadata.get("id") != "calendar-data":
        raise ValueError("3D contribution graph has no date metadata")
    details = json.loads(metadata.text)
    style = next((child.text or "" for child in root if child.tag == tag("style")), "")
    return graph, style, int(details["annual"]), date.fromisoformat(details["through"])


def stat(root, x, y, value, caption):
    text(root, x, y, f"{value:,}", 14, PALE, "bold")
    text(root, x, y + 13, caption, 9, MUTED)


def language_panel(root, metrics):
    counts = metrics["languages"]["counts"]
    total = metrics["languages"]["source_file_changes"]
    ordered = sorted(counts.items(), key=lambda item: item[1], reverse=True)
    text(root, 251, 205, "LANGUAGES · AUTHORED CHANGES (1Y)", 9, BLUE, "bold")
    x = 251.0
    for index, (_, count) in enumerate(ordered):
        width = 219.0 * count / total
        add(root, "rect", {
            "x": f"{x:.2f}", "y": "213", "width": f"{width:.2f}",
            "height": "6", "fill": SHADES[min(index, len(SHADES) - 1)],
        })
        x += width
    for index, (name, count) in enumerate(ordered[:5]):
        x = 251 + (index % 2) * 111
        y = 235 + (index // 2) * 16
        add(root, "circle", {"cx": str(x + 3), "cy": str(y - 3), "r": "2.5",
                             "fill": SHADES[index]})
        text(root, x + 10, y, "%s %.1f%%" % (name, 100 * count / total), 9, PALE)
    text(root, 251, 278, "%s source-file changes · %s repos" %
         (f"{total:,}", metrics["languages"]["repositories"]), 8, MUTED)


def render(metrics, graph, graph_style, annual, through, output):
    root = ET.Element(tag("svg"), {
        "width": "740", "height": "286", "viewBox": "0 0 740 286", "role": "img",
        "aria-label": "Aidan Garske compact GitHub metrics with blue 3D contributions and authored languages",
    })
    add(root, "title", value="Aidan Garske · GitHub metrics")
    add(root, "desc", value="Public GitHub activity and authored source changes across recent contributed repositories; blue 3D calendar generated with yoshi389111/github-profile-3d-contrib")
    add(root, "style", value=graph_style)
    add(root, "rect", {"width": "740", "height": "286", "rx": "8",
                       "fill": "#0d1117", "stroke": "#30363d"})
    add(root, "line", {"x1": "18", "y1": "49", "x2": "722", "y2": "49", "stroke": "#30363d"})
    for x in (236, 488):
        add(root, "line", {"x1": str(x), "y1": "60", "x2": str(x), "y2": "273",
                           "stroke": "#30363d"})

    text(root, 18, 24, metrics["name"], 16, BLUE, "bold")
    text(root, 18, 40, "@%s  ·  %s contributions in the last year" %
         (metrics["login"], f"{annual:,}"), 10)
    add(root, "circle", {"cx": "690", "cy": "26", "r": "18", "fill": "#0d1117",
                         "stroke": BLUE, "stroke-width": "2.5"})
    text(root, 690, 30, metrics["rank"], 11, PALE, "bold", "middle")
    text(root, 662, 29, "GITHUB SCORE", 8, MUTED, anchor="end")

    text(root, 18, 69, "ACCOUNT", 9, BLUE, "bold")
    joined = date.fromisoformat(metrics["joined"]).strftime("%b %Y")
    facts = (
        "Joined %s" % joined,
        "%s public repositories" % metrics["public_repos"],
        "%s followers" % metrics["followers"],
        "%s repositories committed to · 1y" % metrics["repos_with_commits_last_year"],
    )
    for index, fact in enumerate(facts):
        add(root, "circle", {"cx": "20", "cy": str(84 + index * 17), "r": "2", "fill": BLUE})
        text(root, 28, 87 + index * 17, fact, 9.5, PALE)
    text(root, 18, 166, "MOST ACTIVE REPOS · COMMITS (1Y)", 9, BLUE, "bold")
    for index, repo in enumerate(metrics["top_repos"]):
        y = 185 + index * 21
        text(root, 18, y, repo["name"], 9.5, PALE)
        text(root, 220, y, f"{repo['commits']:,}", 9.5, BLUE, "bold", "end")
    text(root, 18, 278, "Public GitHub data · %s" % metrics["as_of"], 8, MUTED)

    text(root, 251, 69, "ACTIVITY", 9, BLUE, "bold")
    stat(root, 251, 91, metrics["commits_last_year"], "commits · 1y")
    stat(root, 362, 91, metrics["prs_opened"], "PRs opened")
    stat(root, 251, 132, metrics["prs_reviewed"], "PRs reviewed")
    stat(root, 362, 132, metrics["issues_opened"], "issues opened")
    stat(root, 251, 173, metrics["threads_commented"], "threads commented on")
    stat(root, 362, 173, metrics["owned_repo_stars"], "stars on my repos")
    language_panel(root, metrics)

    text(root, 503, 69, "3D CONTRIBUTIONS", 9, BLUE, "bold")
    container = add(root, "g", {"transform": "translate(500 75) scale(0.17)"})
    container.append(copy.deepcopy(graph))
    text(root, 503, 245, "%s contributions · last year" % f"{annual:,}", 10, PALE, "bold")
    text(root, 503, 262, "Calendar through %s" % through.strftime("%d %b %Y"), 9, MUTED)
    text(root, 503, 278, "3D calendar by yoshi389111", 8, MUTED)
    output.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(output, encoding="utf-8", xml_declaration=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data/profile-metrics.json"))
    parser.add_argument("--graph", type=Path, default=Path("assets/blue-3d-calendar.svg"))
    parser.add_argument("--output", type=Path, default=Path("assets/profile-metrics-blue.svg"))
    args = parser.parse_args()
    metrics = json.loads(args.data.read_text())
    graph, style, annual, through = graph_data(args.graph)
    render(metrics, graph, style, annual, through, args.output)


if __name__ == "__main__":
    main()
