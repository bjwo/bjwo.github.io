#!/usr/bin/env python3
"""Build the shared overview index used for the grey "other days" layer.

At the overview zoom level every map also draws the routes of the other days
in grey. That layer needs just enough geometry to be recognisable, so each
track is thinned much more aggressively than in assets/tracks/.

Output: assets/tracks/overview.js

    window.TRACK_OVERVIEW = [
      {id: "...", name: "...", url: "/eurovelo7/EV7-Day1-.../", points: [[lat, lon], ...]},
      ...
    ];

Run after tools/gpx_to_js.py:

    python3 tools/gpx_to_js.py && python3 tools/overview_index.py
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_TRACKS = REPO_ROOT / "assets" / "tracks"
DEFAULT_OUT = REPO_ROOT / "assets" / "tracks" / "overview.js"


def post_url_by_id() -> dict[str, str]:
    """Map each tour id to the permalink of the post that embeds it."""
    urls: dict[str, str] = {}
    categories: dict[str, str] = {}
    for post in sorted((REPO_ROOT / "_posts").glob("*.md")):
        text = post.read_text(encoding="utf-8")
        match = re.search(r'route_map\.html id="(\d+)"', text)
        if not match:
            continue
        tidy = post.stem
        # /YYYY-MM-DD-slug -> /category/slug/ ; Jekyll lowercases the category
        # segment and keeps the title's original case.
        body = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", tidy)
        cat = re.search(r"^categories:\s*\n\s*-\s*(\S+)", text, re.M)
        category = cat.group(1).lower() if cat else ""
        urls[match.group(1)] = f"/{category}/{body}/" if category else f"/{body}/"
    return urls


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tracks-dir", type=pathlib.Path, default=DEFAULT_TRACKS)
    parser.add_argument("--out", type=pathlib.Path, default=DEFAULT_OUT)
    parser.add_argument("--step", type=int, default=12, help="keep every Nth point (default 12)")
    args = parser.parse_args()

    urls = post_url_by_id()
    entries = []
    missing = []
    for track_file in sorted(args.tracks_dir.glob("*.js")):
        if track_file.name == "overview.js":
            continue
        tour_id = track_file.stem
        raw = track_file.read_text(encoding="utf-8")
        payload = json.loads(raw[raw.index("= {") + 2 :].rstrip().rstrip(";"))
        points = payload.get("points", [])
        if not points:
            continue
        thinned = [[round(p[0], 4), round(p[1], 4)] for p in points[:: args.step]]
        if thinned[-1] != [round(points[-1][0], 4), round(points[-1][1], 4)]:
            thinned.append([round(points[-1][0], 4), round(points[-1][1], 4)])
        if tour_id not in urls:
            missing.append(tour_id)
        entries.append(
            {
                "id": tour_id,
                "name": payload.get("name", tour_id),
                "url": urls.get(tour_id, ""),
                "points": thinned,
            }
        )

    body = json.dumps(entries, separators=(",", ":"), ensure_ascii=False)
    args.out.write_text(
        "window.TRACK_OVERVIEW = " + body + ";\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(entries)} overview routes to {args.out} ({args.out.stat().st_size // 1024} KB)")
    if missing:
        print(f"  ! no post found for ids: {', '.join(missing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
