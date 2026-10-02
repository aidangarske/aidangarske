#!/usr/bin/env python3
"""Give both profile columns identical responsive dimensions."""

import math
from pathlib import Path
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET


NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", NS)
SKYLINE_URL = "https://gitcity.natrajx.in/api/svg?u=aidangarske&theme=ocean"


def panel(width, height, title):
    root = ET.Element("{%s}svg" % NS, {
        "width": str(width), "height": str(height),
        "viewBox": "0 0 %s %s" % (width, height), "role": "img",
        "aria-label": title,
    })
    ET.SubElement(root, "{%s}title" % NS).text = title
    return root


def write(root, path):
    svg = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    path.write_bytes(b"\n".join(line.rstrip() for line in svg.splitlines()) + b"\n")


def main():
    assets = Path("assets")
    stats = ET.parse(assets / "github-stats.svg").getroot()
    languages = ET.parse(assets / "top-languages.svg").getroot()
    width = int(languages.get("width"))
    stats_height = math.ceil(width * int(stats.get("height")) / int(stats.get("width")))
    languages_height = int(languages.get("height"))
    gap = 12
    height = stats_height + gap + languages_height
    summary = panel(width, height, "Aidan's GitHub stats, yearly languages, and career source lines added")
    stats.set("width", str(width))
    stats.set("height", str(stats_height))
    languages.set("y", str(stats_height + gap))
    summary.extend((stats, languages))

    with urlopen(Request(SKYLINE_URL, headers={"User-Agent": "aidan-profile"}), timeout=60) as response:
        city = ET.fromstring(response.read())
    if city.tag != "{%s}svg" % NS or "GitCity Skyline" not in " ".join(city.itertext()):
        raise ValueError("Skyline provider returned an invalid card")
    skyline = panel(width, height, "Aidan's interactive GitHub contribution skyline")
    ET.SubElement(skyline, "{%s}rect" % NS, {
        "width": str(width), "height": str(height), "rx": "6", "fill": "#020c14",
    })
    city.set("x", "0")
    city.set("y", "0")
    city.set("width", str(width))
    city.set("height", str(height))
    city.set("preserveAspectRatio", "xMidYMid meet")
    skyline.append(city)
    # Write only after all three source cards have loaded successfully.
    write(summary, assets / "profile-summary.svg")
    write(skyline, assets / "profile-skyline.svg")
    print("Both profile panels are %s × %s; skyline proportions preserved" % (width, height))


if __name__ == "__main__":
    main()
