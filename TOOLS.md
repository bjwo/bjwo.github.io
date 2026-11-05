# Route maps

Each tour day shows its route on a map with an altitude profile, built from
local files. No Komoot or third-party tile requests are made at view time.

```
GitHub GPX? --> assets/gpx/<trip>/*.gpx   (source, committed, ~73 MB)
                 |  tools/gpx_to_js.py
                 v
              assets/tracks/<tour-id>.js  (small, committed, ~1.5 MB total)
                 |
                 +--> rendered by _includes/route_map.html + assets/js/route-figure.js
```

## Viewing

```sh
bundle exec jekyll serve      # http://127.0.0.1:4000
```

## Adding or replacing a day

1. Put the GPX in `assets/gpx/<trip>/`. The filename must contain the Komoot
   tour id, e.g. `2019-08-07_84517084_1_ Holmsund - Gideå Bruk.gpx`.
2. Regenerate the small track files:

   ```sh
   python3 tools/gpx_to_js.py
   ```

3. Reference it in the post, with a blank line above and below the include:

   ```liquid
   ## Route

   {% include route_map.html id="84517084" %}
   ```

4. Make sure map tiles exist for the new area (see below), then commit
   `assets/gpx`, `assets/tracks` and `assets/tiles` together.

## Tiles

Tiles are self-hosted under `assets/tiles/<z>/<x>/<y>.png` and only two zoom
levels are committed, **z5 (overview) and z10 (detail)**. The map snaps between
them, because intermediate levels have no tiles.

After adding a route, fetch any missing tiles:

```sh
python3 tools/fetch_tiles.py --zoom 5 --ring 2 --dry-run   # check the count
python3 tools/fetch_tiles.py --zoom 5 --ring 2
python3 tools/fetch_tiles.py --zoom 10 --ring 1
```

`--ring` is the margin *in tiles* around each track (not degrees) so the map
viewport is filled once the route is framed. The script skips tiles that are
already present, so it is safe to re-run.

### Tile provider policy

The default provider is [CyclOSM](https://www.cyclosm.org/), a cycle-oriented
OpenStreetMap render served by OpenStreetMap France, which is a good fit for
cycling content. Attribution (OpenStreetMap + CyclOSM) is rendered on every map.

The script refuses to run against `tile.openstreetmap.org`: that server's
[usage policy](https://operations.osmfoundation.org/policies/tiles/) prohibits
bulk/pre-emptive downloading and offline use. If you change providers, check
that their terms allow pre-fetching first.

`--tile-url` accepts an XYZ endpoint; `{s}` is replaced with `a`/`b`/`c` to
spread requests across the provider's shards.

## Files

| Path | Purpose |
|---|---|
| `assets/gpx/` | Original GPX per tour (committed, not served to visitors) |
| `assets/tracks/` | Decimated lat/lon/elevation JSON per tour id |
| `assets/tiles/` | Self-hosted map tiles, z5 + z10 only |
| `tools/gpx_to_js.py` | GPX → compact track files |
| `tools/fetch_tiles.py` | Downloads the tiles the routes need |
| `_includes/route_map.html` | Markup for one day's map |
| `assets/js/route-figure.js` | Leaflet map + canvas elevation profile |
