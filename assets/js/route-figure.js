/*!
 * Route figure: draws a GPX track on a self-hosted map and renders an
 * altitude profile underneath.
 *
 * Data comes from assets/tracks/<id>.js, which defines
 * window.TRACKS["<id>"] = {name: "...", points: [[lat, lon, ele], ...]}.
 *
 * The map, the elevation chart and the distance/height summary are all built
 * here; no third-party services are contacted.
 */
(function () {
  "use strict";

  // Only these two zoom levels have tiles committed (see tools/fetch_tiles.py).
  // Leaflet cannot skip intermediate levels, so the map snaps between them.
  var ZOOMS = [5, 10];
  var TILE_URL = (document.documentElement.getAttribute("data-tile-base") || "") + "/{z}/{x}/{y}.png";
  var TILE_ATTRIBUTION =
    'Map data &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, ' +
    'style <a href="https://www.cyclosm.org/">CyclOSM</a>';

  function haversine(a, b) {
    var R = 6371000;
    var toRad = Math.PI / 180;
    var dLat = (b[0] - a[0]) * toRad;
    var dLon = (b[1] - a[1]) * toRad;
    var h =
      Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos(a[0] * toRad) * Math.cos(b[0] * toRad) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
    return 2 * R * Math.asin(Math.sqrt(h));
  }

  function summarise(points) {
    var distance = 0;
    var ascent = 0;
    for (var i = 1; i < points.length; i++) {
      distance += haversine(points[i - 1], points[i]);
      var step = points[i][2] - points[i - 1][2];
      if (step > 0) ascent += step;
    }
    return { distance: distance, ascent: ascent };
  }

  function drawMap(container, points, name, trackId) {
    if (typeof L === "undefined") return;

    var minZoom = ZOOMS[0];
    var maxZoom = ZOOMS[ZOOMS.length - 1];
    var map = L.map(container, { scrollWheelZoom: false, minZoom: minZoom, maxZoom: maxZoom });
    L.tileLayer(TILE_URL, {
      minZoom: minZoom,
      maxZoom: maxZoom,
      maxNativeZoom: maxZoom,
      noWrap: true,
      attribution: TILE_ATTRIBUTION,
    }).addTo(map);

    // Only z5 and z10 have tiles, and Leaflet cannot skip levels. Track the
    // last settled level so an in-between zoom can be snapped in the same
    // direction the user was travelling: outwards lands on the overview,
    // inwards on the detail. Snapping to the "nearest" level made zoom-out
    // from z10 jump straight back to z10, which looked broken.
    var settled = maxZoom;
    map.on("zoomend", function () {
      var current = map.getZoom();
      if (ZOOMS.indexOf(current) !== -1) {
        settled = current;
        return;
      }
      var goingOut = current < settled;
      map.setZoom(goingOut ? ZOOMS[0] : ZOOMS[ZOOMS.length - 1]);
    });

    var latlngs = points.map(function (p) { return [p[0], p[1]]; });
    var line = L.polyline(latlngs, { color: "#1f6fb2", weight: 4, opacity: 0.85 }).addTo(map);

    // Reference layer: every other day in grey, so the overview shows where
    // this day sits in the wider trip. Added after the current route so it
    // starts on top, then sent behind it; hover brings a line forward.
    var overview = window.TRACK_OVERVIEW || [];
    overview.forEach(function (entry) {
      if (!entry.points || !entry.points.length) return;
      if (entry.id === trackId) return;

      var grey = L.polyline(
        entry.points.map(function (p) { return [p[0], p[1]]; }),
        { color: "#8a8a8a", weight: 2, opacity: 0.55, interactive: true }
      ).addTo(map);

      var restyle = function (active) {
        grey.setStyle(
          active
            ? { color: "#4a4a4a", weight: 4, opacity: 0.95 }
            : { color: "#8a8a8a", weight: 2, opacity: 0.55 }
        );
        if (active) grey.bringToFront();
        else line.bringToFront();
      };

      grey.bindTooltip(entry.name || entry.id, { sticky: true });
      grey.on("mouseover", function () { restyle(true); });
      grey.on("mouseout", function () { restyle(false); });

      if (entry.url) {
        grey.on("click", function () { window.location.href = entry.url; });
        grey.on("add", function () {
          if (grey._path) grey._path.style.cursor = "pointer";
        });
      }
    });

    line.bringToFront();

    L.circleMarker(latlngs[0], { radius: 6, color: "#1a7f37", fillOpacity: 1 })
      .addTo(map)
      .bindTooltip("Start");
    L.circleMarker(latlngs[latlngs.length - 1], { radius: 6, color: "#b3261e", fillOpacity: 1 })
      .addTo(map)
      .bindTooltip("Finish");

    // Open framed on the route at the most detailed available level. The
    // coarser level is reachable with the zoom-out control, so z5 is an
    // overview rather than the default (at z5 a 100 km day is only a few
    // pixels across).
    map.fitBounds(line.getBounds(), { padding: [24, 24] });
    var detailed = ZOOMS[ZOOMS.length - 1];
    if (map.getZoom() > detailed) map.setZoom(detailed);
    // Initial fit may have passed through intermediate levels; treat the
    // resulting view as the starting point for the direction tracking above.
    if (ZOOMS.indexOf(map.getZoom()) !== -1) settled = map.getZoom();

    return map;
  }

  function drawChart(container, points, hoverMarker) {
    var width = container.clientWidth || 600;
    var height = 150;
    var pad = { top: 12, right: 8, bottom: 22, left: 38 };

    var cumulative = [0];
    for (var i = 1; i < points.length; i++) {
      cumulative.push(cumulative[i - 1] + haversine(points[i - 1], points[i]));
    }
    var total = cumulative[cumulative.length - 1] || 1;
    var elevations = points.map(function (p) { return p[2]; });
    var minEle = Math.min.apply(null, elevations);
    var maxEle = Math.max.apply(null, elevations);
    var span = Math.max(maxEle - minEle, 10);
    minEle = Math.max(0, minEle - span * 0.1);
    maxEle = maxEle + span * 0.1;

    var canvas = document.createElement("canvas");
    var ratio = window.devicePixelRatio || 1;
    canvas.width = width * ratio;
    canvas.height = height * ratio;
    canvas.style.width = width + "px";
    canvas.style.height = height + "px";
    container.appendChild(canvas);

    var ctx = canvas.getContext("2d");
    ctx.scale(ratio, ratio);
    ctx.clearRect(0, 0, width, height);

    var plotW = width - pad.left - pad.right;
    var plotH = height - pad.top - pad.bottom;
    function xAt(dist) { return pad.left + (dist / total) * plotW; }
    function yAt(ele) { return pad.top + (1 - (ele - minEle) / (maxEle - minEle)) * plotH; }

    // filled area
    ctx.beginPath();
    ctx.moveTo(xAt(0), yAt(points[0][2]));
    for (var j = 1; j < points.length; j++) ctx.lineTo(xAt(cumulative[j]), yAt(points[j][2]));
    ctx.lineTo(xAt(total), pad.top + plotH);
    ctx.lineTo(pad.left, pad.top + plotH);
    ctx.closePath();
    ctx.fillStyle = "rgba(31, 111, 178, 0.18)";
    ctx.fill();

    // profile line
    ctx.beginPath();
    ctx.moveTo(xAt(0), yAt(points[0][2]));
    for (var k = 1; k < points.length; k++) ctx.lineTo(xAt(cumulative[k]), yAt(points[k][2]));
    ctx.strokeStyle = "#1f6fb2";
    ctx.lineWidth = 1.5;
    ctx.stroke();

    // axes
    ctx.strokeStyle = "rgba(0, 0, 0, 0.2)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(pad.left, pad.top);
    ctx.lineTo(pad.left, pad.top + plotH);
    ctx.lineTo(pad.left + plotW, pad.top + plotH);
    ctx.stroke();

    ctx.fillStyle = "rgba(0, 0, 0, 0.65)";
    ctx.font = "11px system-ui, sans-serif";
    ctx.textAlign = "right";
    ctx.fillText(Math.round(maxEle) + " m", pad.left - 4, pad.top + 8);
    ctx.fillText(Math.round(minEle) + " m", pad.left - 4, pad.top + plotH);
    ctx.textAlign = "center";
    ctx.fillText("0 km", pad.left, height - 6);
    ctx.fillText((total / 1000).toFixed(0) + " km", pad.left + plotW, height - 6);

    var hoverLine = document.createElement("div");
    hoverLine.className = "route-figure__cursor";
    container.style.position = "relative";
    container.appendChild(hoverLine);

    container.addEventListener("mousemove", function (event) {
      var rect = canvas.getBoundingClientRect();
      var px = event.clientX - rect.left;
      var fraction = Math.min(1, Math.max(0, (px - pad.left) / plotW));
      var target = fraction * total;
      var nearest = 0;
      for (var n = 1; n < cumulative.length; n++) {
        if (Math.abs(cumulative[n] - target) < Math.abs(cumulative[nearest] - target)) nearest = n;
      }
      hoverLine.style.display = "block";
      hoverLine.style.left = xAt(cumulative[nearest]) + "px";
      container.setAttribute(
        "data-readout",
        (cumulative[nearest] / 1000).toFixed(1) + " km · " + Math.round(points[nearest][2]) + " m"
      );
      if (hoverMarker) hoverMarker(latlngOf(points[nearest]));
    });

    container.addEventListener("mouseleave", function () {
      hoverLine.style.display = "none";
      container.removeAttribute("data-readout");
      if (hoverMarker) hoverMarker(null);
    });
  }

  function latlngOf(point) {
    return [point[0], point[1]];
  }

  function init(figure) {
    var id = figure.getAttribute("data-track-id");
    var track = window.TRACKS && window.TRACKS[id];
    if (!track || !track.points || !track.points.length) return;

    var mapEl = figure.querySelector(".route-figure__map");
    var chartEl = figure.querySelector(".route-figure__chart");
    var metaEl = figure.querySelector(".route-figure__meta");

    var stats = summarise(track.points);
    if (metaEl) {
      metaEl.textContent =
        Math.round(stats.distance / 1000) + " km · " + Math.round(stats.ascent) + " m ascent";
    }

    var map = mapEl ? drawMap(mapEl, track.points, track.name, id) : null;
    var marker = null;
    if (map) {
      marker = L.circleMarker(track.points[0], { radius: 5, color: "#b3261e", fillOpacity: 0.9 });
    }
    if (chartEl) {
      drawChart(chartEl, track.points, function (latlng) {
        if (!map || !marker) return;
        if (!latlng) {
          marker.remove();
          return;
        }
        marker.setLatLng(latlng).addTo(map);
      });
    }
  }

  function start() {
    var figures = document.querySelectorAll(".route-figure");
    for (var i = 0; i < figures.length; i++) init(figures[i]);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
