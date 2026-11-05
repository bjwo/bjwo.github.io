#!/usr/bin/env python3
"""Convert the GPX tracks in assets/gpx/ into small per-tour JavaScript files.

Each tour ``<id>`` gets ``assets/tracks/<id>.js`` containing::

    window.TRACKS = window.TRACKS || {};
    window.TRACKS["<id>"] = {name: "...", points: [[lat, lon, ele], ...]};

Points are thinned with a distance threshold so the files stay small (a few
KB each) while keeping the shape of the route and the climb profile. The raw
GPX is never served to visitors.

Run it again whenever a track is added or replaced::

    python3 tools/gpx_to_js.py
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import re
import xml.etree.ElementTree as ET

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_GPX = REPO_ROOT / "assets" / "gpx"
DEFAULT_OUT = REPO_ROOT / "assets" / "tracks"
GPX_NS = {"g": "http://www.topografix.com/GPX/1/1"}


def haversine(a: tuple[float, float], b: tuple[float, float]) -> float:
    radius = 6_371_000.0
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(h))


def read_track(gpx: pathlib.Path) -> tuple[str, list[tuple[float, float, float]]]:
    root = ET.parse(gpx).getroot()
    name = (root.findtext(".//g:trk/g:name", default="", namespaces=GPX_NS) or gpx.stem).strip()
    points = []
    for pt in root.iterfind(".//g:trkpt", GPX_NS):
        ele = pt.findtext("g:ele", default=None, namespaces=GPX_NS)
        points.append((float(pt.get("lat")), float(pt.get("lon")), float(ele) if ele else 0.0))
    return name, points


def thin(points: list[tuple[float, float, float]], min_distance: float) -> list[list[float]]:
    """Keep a point when it is at least min_distance metres from the last kept one."""
    if not points:
        return []
    kept = [points[0]]
    for point in points[1:]:
        if haversine(kept[-1][:2], point[:2]) >= min_distance:
            kept.append(point)
    if kept[-1] != points[-1]:
        kept.append(points[-1])
    return [[round(lat, 5), round(lon, 5), round(ele)] for lat, lon, ele in kept]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--gpx-dir", type=pathlib.Path, default=DEFAULT_GPX)
    parser.add_argument("--out", type=pathlib.Path, default=DEFAULT_OUT)
    parser.add_argument("--spacing", type=float, default=100.0, help="metres between kept points (default 100)")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    conversions = 0
    for gpx in sorted(args.gpx_dir.rglob("*.gpx")):
        match = re.search(r"_(\d{6,})_", gpx.name)
        if not match:
            print(f"  ! no tour id in {gpx.name}, skipping")
            continue
        tour_id = match.group(1)
        try:
            name, points = read_track(gpx)
        except ET.ParseError as exc:
            print(f"  ! unreadable {gpx.name}: {exc}")
            continue
        thinned = thin(points, args.spacing)
        payload = json.dumps({"name": name, "points": thinned}, separators=(",", ":"), ensure_ascii=False)
        target = args.out / f"{tour_id}.js"
        target.write_text(
            "window.TRACKS = window.TRACKS || {};\n"
            f'window.TRACKS["{tour_id}"] = {payload};\n',
            encoding="utf-8",
        )
        conversions += 1
        print(f"  {tour_id}: {len(points)} -> {len(thinned)} points, {target.stat().st_size // 1024} KB")
    print(f"Wrote {conversions} track files to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
