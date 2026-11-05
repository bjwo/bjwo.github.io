#!/usr/bin/env python3
"""Slice OpenStreetMap raster tiles into a self-hosted XYZ tree.

Usage::

    python3 tools/fetch_tiles.py --zoom 11
    python3 tools/fetch_tiles.py --zoom 10 --zoom 11 --out assets/tiles
    python3 tools/fetch_tiles.py --zoom 11 --dry-run

Every route is read from assets/gpx/**/*.gpx; the union of the tiles covered
by all routes at the requested zoom levels is written to
``<out>/<z>/<x>/<y>.png``, which is the layout Leaflet expects from a
``{z}/{x}/{y}`` tile URL template.

The script is polite (one request at a time, configurable delay, clear
User-Agent naming this site), but it performs a bulk download, so it refuses
to run against tile.openstreetmap.org: that server's usage policy forbids
pre-fetching and offline use. Point --tile-url at a provider that permits it,
or host your own tiles. See TOOLS.md for the options and caveats.

This is a one-off preparation step; its output is committed as static files,
so no network access is needed at build or view time.
"""

from __future__ import annotations

import argparse
import math
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_GPX = REPO_ROOT / "assets" / "gpx"
DEFAULT_OUT = REPO_ROOT / "assets" / "tiles"
# The site lives under /<repo>/ on GitHub Pages, so the tiles are served from
# {site.baseurl}/assets/tiles/. This is only used for display here.
# {s} is replaced with a/b/c to spread requests over CyclOSM's tile servers
DEFAULT_URL = "https://{s}.tile-cyclosm.openstreetmap.fr/cyclosm"
# CyclOSM (a cycle-oriented OSM render served by OpenStreetMap France) is the
# chosen provider; see TOOLS.md for the policy discussion. The guard below
# still blocks tile.openstreetmap.org, which forbids pre-fetching outright.
BLOCKED_HOSTS = {"tile.openstreetmap.org", "a.tile.openstreetmap.org", "b.tile.openstreetmap.org", "c.tile.openstreetmap.org"}
USER_AGENT = "bjwo.github.io static tile archive (https://bjwo.de)"


def tile_x(lon: float, zoom: int) -> int:
    n = 2**zoom
    return int((lon + 180.0) / 360.0 * n)


def tile_y(lat: float, zoom: int) -> int:
    n = 2**zoom
    rad = math.radians(lat)
    return int((1 - math.log(math.tan(rad) + 1 / math.cos(rad)) / math.pi) / 2 * n)


def route_points(gpx: pathlib.Path) -> list[tuple[float, float]]:
    """Return (lat, lon) for every track point in a GPX file."""
    import xml.etree.ElementTree as ET

    ns = {"g": "http://www.topografix.com/GPX/1/1"}
    try:
        root = ET.parse(gpx).getroot()
    except ET.ParseError as exc:  # pragma: no cover - defensive
        print(f"  ! skipping unreadable file {gpx.name}: {exc}", file=sys.stderr)
        return []
    return [
        (float(pt.get("lat")), float(pt.get("lon")))
        for pt in root.iterfind(".//g:trkpt", ns)
    ]


def tiles_for_zoom(gpx_files: list[pathlib.Path], zoom: int, ring: int = 2) -> set[tuple[int, int]]:
    """Tiles covering every track, expanded by ``ring`` tiles on each side.

    The padding is measured in tiles, not degrees: the map viewport is always
    wider than the route line, and a fixed degree margin rounds down to the same
    tile at these latitudes, which left the area around the track blank.
    """
    tiles: set[tuple[int, int]] = set()
    for gpx in gpx_files:
        for lat, lon in route_points(gpx):
            cx, cy = tile_x(lon, zoom), tile_y(lat, zoom)
            for dx in range(-ring, ring + 1):
                for dy in range(-ring, ring + 1):
                    tiles.add((cx + dx, cy + dy))
    return tiles


SUBDOMAINS = "abc"


def fetch(tile_url: str, zoom: int, x: int, y: int, index: int = 0) -> bytes:
    base = tile_url.replace("{s}", SUBDOMAINS[index % len(SUBDOMAINS)])
    url = f"{base}/{zoom}/{x}/{y}.png"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--zoom", type=int, action="append", help="zoom level (repeatable, default 11)")
    parser.add_argument("--gpx-dir", type=pathlib.Path, default=DEFAULT_GPX)
    parser.add_argument("--out", type=pathlib.Path, default=DEFAULT_OUT)
    parser.add_argument("--limit", type=int, default=0, help="only read the first N GPX files (useful for testing)")
    parser.add_argument("--ring", type=int, default=2,
                        help="tiles of margin around each track (default 2)")
    parser.add_argument("--tile-url", default=DEFAULT_URL, help="upstream XYZ tile endpoint")
    parser.add_argument("--delay", type=float, default=0.2, help="seconds between requests (default 0.2)")
    parser.add_argument("--dry-run", action="store_true", help="only report how many tiles would be fetched")
    args = parser.parse_args()

    zooms = args.zoom or [11]

    host = urllib.parse.urlparse(args.tile_url).hostname or ""
    if host in BLOCKED_HOSTS:
        print(
            "Refusing to run against tile.openstreetmap.org.\n"
            "Their usage policy prohibits bulk downloading and offline use of tiles:\n"
            "  https://operations.osmfoundation.org/policies/tiles/\n"
            "Choose a provider that permits it, or run your own tiles. See TOOLS.md.",
            file=sys.stderr,
        )
        return 3

    gpx_files = sorted(args.gpx_dir.rglob("*.gpx"))
    if args.limit:
        gpx_files = gpx_files[: args.limit]
    if not gpx_files:
        print(f"No GPX files found under {args.gpx_dir}", file=sys.stderr)
        return 1
    print(f"Reading {len(gpx_files)} GPX files")

    total_written = total_skipped = total_failed = 0
    for zoom in zooms:
        tiles = sorted(tiles_for_zoom(gpx_files, zoom, args.ring))
        print(f"z{zoom}: {len(tiles)} tiles")
        if args.dry_run:
            continue
        for index, (x, y) in enumerate(tiles, start=1):
            dest = args.out / str(zoom) / str(x) / f"{y}.png"
            if dest.exists() and dest.stat().st_size > 0:
                total_skipped += 1
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                data = fetch(args.tile_url, zoom, x, y, index)
            except (urllib.error.URLError, TimeoutError) as exc:
                total_failed += 1
                print(f"  ! {zoom}/{x}/{y} failed: {exc}", file=sys.stderr)
                continue
            dest.write_bytes(data)
            total_written += 1
            if index % 50 == 0:
                print(f"  {index}/{len(tiles)}")
            time.sleep(args.delay)

    print(f"Done: {total_written} written, {total_skipped} already present, {total_failed} failed")
    try:
        shown = args.out.resolve().relative_to(REPO_ROOT)
    except ValueError:
        shown = args.out
    print(f"Commit {shown} to ship the tiles with the site.")
    return 0 if total_failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
