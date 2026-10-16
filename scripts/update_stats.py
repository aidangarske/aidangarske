#!/usr/bin/env python3
"""Keep the original hosted stats card and align lifetime PR activity."""

import copy
import json
from pathlib import Path
import re
import subprocess
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET


NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", NS)
URL = (
    "https://github-readme-stats-eight-theta.vercel.app/api?username=aidangarske"
    "&include_all_commits=true&show_icons=true&title_color=58A6FF"
    "&icon_color=58A6FF&text_color=C9D1D9&bg_color=020C14&hide_border=true"
)


def count(query):
    response = subprocess.run(
        ["gh", "api", "search/issues", "-X", "GET", "-f", "q=" + query,
         "-f", "per_page=1"], capture_output=True, text=True, check=True, timeout=60,
    )
    data = json.loads(response.stdout)
    if data.get("incomplete_results"):
        raise ValueError("GitHub returned incomplete PR totals")
    return data["total_count"]


def main():
    with urlopen(Request(URL, headers={"User-Agent": "aidan-profile"}), timeout=60) as response:
        root = ET.fromstring(response.read())
    texts = [node.text.strip() for node in root.findall(".//{%s}text" % NS) if node.text]
    if root.tag != "{%s}svg" % NS or "Total Commits:" not in texts:
        raise ValueError("Original stats provider returned an invalid card")
    merged = count("author:aidangarske type:pr is:merged is:public")
    reviewed = count("reviewed-by:aidangarske -author:aidangarske type:pr is:public")
    width, height = int(root.get("width")), int(root.get("height"))
    root.set("height", str(height + 50))
    root.set("viewBox", "0 0 %s %s" % (width, height + 50))
    # Saved cards must remain readable in viewers that do not run SVG animations.
    styles = " ".join(node.text or "" for node in root.findall("{%s}style" % NS))
    final_offset = re.search(r"to\s*\{\s*stroke-dashoffset:\s*([\d.]+)", styles)
    style = ET.SubElement(root, "{%s}style" % NS)
    style.text = "* { animation: none !important; } .header, .stagger, .rank-text { opacity: 1 !important; }"
    if final_offset:
        style.text += " .rank-circle { stroke-dashoffset: %s !important; }" % final_offset.group(1)
    body = root.find("{%s}g[@data-testid='main-card-body']" % NS)
    rows = body.find("{%s}svg" % NS)
    template = next(row for row in rows if row.find(".//{%s}text[@data-testid='prs']" % NS) is not None)
    for index, (label, value, key) in enumerate((
        ("PRs merged:", merged, "prs-merged"),
        ("PRs reviewed:", reviewed, "prs-reviewed"),
    )):
        row = copy.deepcopy(template)
        texts = row.findall(".//{%s}text" % NS)
        texts[0].text = label
        texts[1].text = f"{value:,}"
        texts[1].set("data-testid", key)
        rows.insert(3 + index, row)
    for index, row in enumerate(rows):
        row.set("transform", "translate(0, %s)" % (index * 27))
        for text in row.findall(".//{%s}text" % NS):
            text.set("y", "14")
            text.set("style", "font-size: 16px")
    new_height = height + 50 + 12
    root.set("height", str(new_height))
    root.set("viewBox", "0 0 %s %s" % (width, new_height))
    rank = body.find("{%s}g[@data-testid='rank-circle']" % NS)
    rank.set("transform", "translate(400, 82)")
    rank.find("{%s}g[@class='rank-text']" % NS).set("transform", "translate(-10, 8)")
    style.text += " .header { font-size: 20px; }"
    metadata = ET.SubElement(root, "{%s}metadata" % NS, {"id": "additional-pr-stats"})
    metadata.text = json.dumps({"provider": URL, "merged": merged, "reviewed": reviewed})
    output = Path("assets/github-stats.svg")
    output.parent.mkdir(parents=True, exist_ok=True)
    svg = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    output.write_bytes(b"\n".join(line.rstrip() for line in svg.splitlines()) + b"\n")
    print("Preserved original stats card; added %s merged and %s reviewed PRs" % (merged, reviewed))


if __name__ == "__main__":
    main()
