#!/usr/bin/env python3
"""Build one compact SVG from the blue 3D graph and public GitHub data."""

import argparse
import copy
import json
import os
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET


NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", NS)
USER = "aidangarske"
BLUE = "#58a6ff"
PALE = "#c9d1d9"
MUTED = "#8b949e"
SHADES = ("#15446e", "#1c66a0", "#2386c3", "#329fd4", "#62b9e7", "#9ad8f5")
STATS_URL = (
    "https://github-readme-stats-eight-theta.vercel.app/api?"
    "username=aidangarske&include_all_commits=true&show_icons=true&"
    "title_color=58A6FF&icon_color=58A6FF&text_color=C9D1D9&"
    "bg_color=020C14&hide_border=true"
)
LANGUAGES_URL = (
    "https://github-readme-stats-eight-theta.vercel.app/api/top-langs/?"
    "username=aidangarske&layout=compact&langs_count=6&"
    "title_color=58A6FF&text_color=C9D1D9&bg_color=020C14&"
    "hide_border=true&hide=html,css"
)


def tag(name):
    return "{%s}%s" % (NS, name)


def fetch(url, github=False):
    headers = {"User-Agent": "aidangarske-profile-metrics", "Accept": "image/svg+xml"}
    if github:
        headers["Accept"] = "application/vnd.github+json"
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = "Bearer " + token
    with urlopen(Request(url, headers=headers), timeout=30) as response:
        return response.read()


def source_bytes(name, url, fixtures=None, github=False):
    if fixtures:
        return (fixtures / name).read_bytes()
    return fetch(url, github=github)


def image_texts(data):
    root = ET.fromstring(data)
    return ["".join(node.itertext()).strip() for node in root.iter(tag("text"))]


def score_data(fixtures):
    texts = image_texts(source_bytes("aidan-score-blue.svg", STATS_URL, fixtures))
    values = {}
    for index, value in enumerate(texts[:-1]):
        if value.endswith(":"):
            values[value[:-1]] = texts[index + 1]
    rank = next((value for value in texts if re.fullmatch(r"[A-F]\+{0,2}", value)), None)
    if not rank or "Total Commits" not in values or "Contributed to" not in values:
        raise ValueError("Score card is missing expected fields")
    return rank, values


def language_data(fixtures):
    texts = image_texts(source_bytes("aidan-languages-blue.svg", LANGUAGES_URL, fixtures))
    languages = []
    for value in texts:
        match = re.fullmatch(r"(.+?) \(([0-9.]+)%\)", value)
        if match:
            languages.append((match.group(1), float(match.group(2))))
    if not languages:
        raise ValueError("Languages card has no language data")
    return languages[:6]


def search_count(query, name, fixtures):
    url = "https://api.github.com/search/issues?" + urlencode({"q": query, "per_page": 1})
    data = json.loads(source_bytes("aidan-search-%s.json" % name, url, fixtures, github=True))
    if data.get("incomplete_results"):
        raise ValueError("GitHub search results are incomplete for " + name)
    return int(data["total_count"])


def graph_data(path):
    root = ET.parse(path).getroot()
    children = list(root)
    graph = next((child for child in children if child.tag == tag("g") and len(child) > 300), None)
    if graph is None:
        raise ValueError("3D graph group was not found")
    metadata = root.find(tag("metadata"))
    if metadata is not None and metadata.get("id") == "calendar-data":
        details = json.loads(metadata.text)
        annual = int(details["annual"])
        through = date.fromisoformat(details["through"])
    else:
        texts = ["".join(node.itertext()).strip() for node in root.iter(tag("text"))]
        index = texts.index("contributions")
        annual = int(re.sub(r"\D", "", texts[index - 1]))
        period = next(value for value in texts if re.fullmatch(r"\d{4}-\d{2}-\d{2} / \d{4}-\d{2}-\d{2}", value))
        through = date.fromisoformat(period.split(" / ")[1])
    style = next((child.text or "" for child in children if child.tag == tag("style")), "")
    return graph, style, annual, through


def add(parent, name, attrs=None, value=None):
    element = ET.SubElement(parent, tag(name), attrs or {})
    if value is not None:
        element.text = str(value)
    return element


def label(root, x, y, value, size=12, color=MUTED, weight="normal", anchor=None):
    attrs = {
        "x": str(x), "y": str(y), "fill": color,
        "font-family": "Arial, Helvetica, sans-serif",
        "font-size": str(size), "font-weight": weight,
    }
    if anchor:
        attrs["text-anchor"] = anchor
    return add(root, "text", attrs, value)


def render(graph, graph_style, annual, through, rank, score, languages, counts, output):
    root = ET.Element(tag("svg"), {
        "width": "740", "height": "360", "viewBox": "0 0 740 360", "role": "img",
        "aria-label": "Aidan Garske GitHub activity, languages, and blue 3D contribution calendar",
    })
    add(root, "title", value="Aidan Garske GitHub metrics")
    add(root, "desc", value="Blue 3D contributions by yoshi389111, with public GitHub activity and language statistics")
    add(root, "style", value=graph_style)
    add(root, "rect", {"width": "740", "height": "360", "rx": "12", "fill": "#0d1117", "stroke": "#30363d"})
    add(root, "line", {"x1": "292", "y1": "72", "x2": "292", "y2": "331", "stroke": "#30363d"})

    label(root, 24, 37, "Aidan Garske", 23, BLUE, "bold")
    label(root, 24, 56, "@aidangarske  ·  %s contributions in the last year" % f"{annual:,}", 12)
    add(root, "circle", {"cx": "688", "cy": "37", "r": "23", "fill": "#0d1117", "stroke": BLUE, "stroke-width": "4"})
    label(root, 688, 42, rank, 14, PALE, "bold", "middle")

    label(root, 24, 84, "ACTIVITY", 12, BLUE, "bold")
    stats = (
        (score["Total Commits"], "commits"),
        (f"{counts['prs']:,}", "PRs opened"),
        (f"{counts['reviewed']:,}", "PRs reviewed"),
        (f"{counts['issues']:,}", "issues opened"),
        (f"{counts['commented']:,}", "threads commented on"),
        (score["Contributed to"], "repos contributed to"),
    )
    for index, (value, caption) in enumerate(stats):
        x = 24 + (index % 2) * 136
        y = 111 + (index // 2) * 42
        label(root, x, y, value, 18, PALE, "bold")
        label(root, x, y + 15, caption, 10, MUTED)

    label(root, 24, 231, "TOP LANGUAGES", 12, BLUE, "bold")
    x = 24.0
    for index, (_, percent) in enumerate(languages):
        width = 248 * percent / 100
        add(root, "rect", {"x": f"{x:.2f}", "y": "242", "width": f"{width:.2f}", "height": "7", "fill": SHADES[index]})
        x += width
    for index, (name, percent) in enumerate(languages[:4]):
        col, row = index % 2, index // 2
        x, y = 24 + col * 136, 271 + row * 25
        add(root, "circle", {"cx": str(x + 4), "cy": str(y - 4), "r": "4", "fill": SHADES[index]})
        label(root, x + 13, y, "%s  %.1f%%" % (name, percent), 11, PALE)

    label(root, 312, 83, "3D CONTRIBUTIONS", 12, BLUE, "bold")
    container = add(root, "g", {"transform": "translate(300 55) scale(0.34)"})
    container.append(copy.deepcopy(graph))
    label(root, 24, 343, "Calendar through %s" % through.strftime("%d %b %Y"), 10, MUTED)
    output.parent.mkdir(parents=True, exist_ok=True)
    ET.ElementTree(root).write(output, encoding="utf-8", xml_declaration=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--graph", type=Path, default=Path("assets/blue-3d-calendar.svg"))
    parser.add_argument("--output", type=Path, default=Path("assets/profile-metrics-blue.svg"))
    parser.add_argument("--fixtures", type=Path)
    args = parser.parse_args()
    graph, style, annual, through = graph_data(args.graph)
    rank, score = score_data(args.fixtures)
    languages = language_data(args.fixtures)
    counts = {
        "prs": search_count("author:%s type:pr" % USER, "prs", args.fixtures),
        "issues": search_count("author:%s type:issue" % USER, "issues", args.fixtures),
        "reviewed": search_count("reviewed-by:%s type:pr" % USER, "reviewed", args.fixtures),
        "commented": search_count("commenter:%s" % USER, "commented", args.fixtures),
    }
    render(graph, style, annual, through, rank, score, languages, counts, args.output)


if __name__ == "__main__":
    main()
