/*
 * The chart. Leaflet over the game's own map tiles, in a flat pixel CRS.
 *
 * The world is 499,200 m square; x is northing from the south edge, z
 * easting. Leaflet's CRS.Simple takes (lat, lng) as (y, x) in a plane where
 * y grows downward at zoom 0 through the transformation below, so a world
 * point becomes latlng = [-(WORLD - x) / M0, z / M0] with M0 the metres per
 * pixel at zoom 0 (61 m). The three tile levels are zooms 0..2; Leaflet
 * scales the finest level for anything closer.
 */
(function () {
    "use strict";

    const WORLD = 499200;
    const M0 = WORLD / (1024 * 8);           // m/px at zoom 0
    const BORDER = 30000;                    // paper margin the tiles include
    const ICONS = {
        airfield: '<svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="6"/><path d="M4 8h8M8 4v8"/></svg>',
        base: '<svg viewBox="0 0 16 16"><circle cx="8" cy="8" r="6.5"/><circle cx="8" cy="8" r="2.2" class="fill"/></svg>'
    };

    const toLatLng = (x, z) => [-(WORLD - x) / M0, z / M0];

    function paperBounds() {
        return L.latLngBounds(toLatLng(0, 0), toLatLng(WORLD, WORLD));
    }

    function createMap(el, options) {
        const map = L.map(el, Object.assign({
            crs: L.CRS.Simple,
            minZoom: -3, maxZoom: 4,
            zoomSnap: 0.25, zoomDelta: 0.5,
            attributionControl: false,
            // Room past the edge, or a route along the coast cannot be centred.
            maxBounds: paperBounds().pad(0.6), maxBoundsViscosity: 0.6,
            zoomControl: true
        }, options || {}));
        // The layer's own zoom range must cover the map's, or a fractional
        // zoom below 0 leaves it with no tile level at all.
        L.tileLayer("/api/maptile/{z}/{y}/{x}", {
            minZoom: -3, maxZoom: 4, minNativeZoom: -2, maxNativeZoom: 2, tileSize: 1024,
            bounds: paperBounds(), noWrap: true, keepBuffer: 1
        }).addTo(map);
        // A view before any vector layer is added: the SVG renderer sizes
        // itself from the first view, and a polyline added before one throws.
        map.setView(toLatLng(WORLD / 2, WORLD / 2), -2);
        // Town names are clutter from afar; a class the stylesheet keys on.
        const far = () => el.classList.toggle("map-far", map.getZoom() < 1);
        map.on("zoomend", far);
        far();
        return map;
    }

    // Place names, as a pane that switches on and off as one.
    let overlayCache = null;
    async function overlayFeatures() {
        if (overlayCache) return overlayCache;
        const r = await fetch("/api/map/overlay");
        overlayCache = r.ok ? (await r.json()).features : [];
        return overlayCache;
    }

    function labelLayer(features) {
        const group = L.layerGroup();
        features.forEach((f) => {
            if (f.kind === "airfield") {
                L.marker(toLatLng(f.x, f.z), {
                    icon: L.divIcon({className: "map-airfield", html: ICONS.airfield +
                        '<span class="map-label">' + esc(f.name) + "</span>", iconSize: [16, 16], iconAnchor: [8, 8]}),
                    interactive: false, keyboard: false
                }).addTo(group);
            } else if (f.kind === "city" && f.name) {
                L.marker(toLatLng(f.x, f.z), {
                    icon: L.divIcon({className: "map-city", html: '<span class="map-label">' + esc(f.name) + "</span>",
                        iconSize: [0, 0], iconAnchor: [0, 0]}),
                    interactive: false, keyboard: false
                }).addTo(group);
            }
        });
        return group;
    }

    function esc(s) {
        return String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
            ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
    }

    // One route: a line through the briefed waypoints, the target ringed,
    // take-off and landing as a base mark. `dim` for the career overview,
    // where dozens overlap.
    function routeLayer(route, dim, T) {
        const group = L.layerGroup();
        const pts = route.points.map((p) => toLatLng(p[0], p[1]));
        const line = L.polyline(pts, {
            className: "map-route" + (dim ? " dim" : ""),
            weight: dim ? 1.5 : 2.5, interactive: !!dim
        }).addTo(group);
        if (dim && T) {
            line.bindTooltip(T("debrief.mission", {number: route.number}) + " · " + route.date +
                " · " + esc(route.type), {sticky: true, className: "map-tip"});
            line.on("click", () => document.dispatchEvent(
                new CustomEvent("map:mission", {detail: route.mission_id})));
        }
        if (!dim) {
            route.points.forEach((p, i) => {
                if (p[2] === 0 || p[2] === 3) return;
                L.marker(toLatLng(p[0], p[1]), {
                    icon: L.divIcon({className: "map-wp" + (p[2] === 2 ? " target" : ""),
                        html: "<span>" + i + "</span>", iconSize: [18, 18], iconAnchor: [9, 9]}),
                    interactive: false
                }).addTo(group);
            });
        }
        return group;
    }

    // The briefed target. On the overview the ring is weighted by what the
    // mission destroyed there, so a sweep that found nothing is a pinprick
    // and the day the squadron flattened an airfield is a big ring - one
    // symbol per mission, where dots for ~1,500 ground kills would carpet
    // every target area.
    function targetMarker(t, dim, route, T) {
        if (!t) return null;
        let radius = dim ? 4 : 9;
        if (dim && route) {
            radius = Math.min(22, 3 + Math.sqrt(route.ground || 0) * 1.4 + (route.air || 0) * 0.8);
        }
        const m = L.circleMarker(toLatLng(t.x, t.z), {
            className: "map-target" + (dim ? " dim" : ""), radius: radius, interactive: !!(dim && route)
        });
        if (dim && route && T) {
            m.bindTooltip(T("debrief.mission", {number: route.number}) + " · " + esc(route.date) +
                " · " + esc(route.type) + "<br>" +
                T("map.target_tip", {ground: route.ground || 0, air: route.air || 0}),
                {className: "map-tip", direction: "top", offset: [0, -radius]});
            m.on("click", () => document.dispatchEvent(
                new CustomEvent("map:mission", {detail: route.mission_id})));
        }
        return m;
    }

    // A ground kill on the mission map: small, muted, but named on hover -
    // what it was, who got it, and how many alike fell in the same pass.
    function groundMarker(k, T) {
        const m = L.circleMarker(toLatLng(k.x, k.z), {className: "map-ground", radius: 3.5});
        const many = k.count > 1 ? " ×" + k.count : "";
        m.bindTooltip(esc(k.target) + many + (k.actor ? " — " + esc(k.actor) : ""),
            {className: "map-tip", direction: "top", offset: [0, -4]});
        return m;
    }

    function victoryMarker(v, T) {
        const m = L.circleMarker(toLatLng(v.x, v.z), {className: "map-victory", radius: 5});
        const who = v.pilot ? esc(v.pilot) + " — " : "";
        m.bindTooltip(who + esc(v.target) + (v.victim ? " <i>" + esc(v.victim) + "</i>" : "") +
            (v.alt ? " · " + v.alt + " m" : "") + "<br>" +
            T("debrief.mission", {number: v.number}) + " · " + v.date,
            {className: "map-tip", direction: "top", offset: [0, -6]});
        m.on("click", () => document.dispatchEvent(
            new CustomEvent("map:mission", {detail: v.mission_id})));
        return m;
    }

    function baseMarker(b, T) {
        return L.marker(toLatLng(b.x, b.z), {
            icon: L.divIcon({className: "map-base", html: ICONS.base, iconSize: [18, 18], iconAnchor: [9, 9]}),
            keyboard: false
        }).bindTooltip(T("map.base_tip", {first: b.first, last: b.last, sorties: b.sorties}),
            {className: "map-tip", direction: "top", offset: [0, -8]});
    }

    function fitTo(map, layers, pad) {
        let bounds = null;
        const walk = (l) => {
            if (l.eachLayer && !l.getBounds) { l.eachLayer(walk); return; }
            const b = l.getBounds ? l.getBounds() : (l.getLatLng ? L.latLngBounds([l.getLatLng()]) : null);
            if (b && b.isValid()) bounds = bounds ? bounds.extend(b) : L.latLngBounds(b);
        };
        layers.forEach(walk);
        if (bounds && bounds.isValid()) map.fitBounds(bounds.pad(pad == null ? 0.15 : pad));
        else map.fitBounds(L.latLngBounds(toLatLng(BORDER, BORDER), toLatLng(WORLD - BORDER, WORLD - BORDER)));
    }

    window.KoreaMap = {createMap, overlayFeatures, labelLayer, routeLayer, targetMarker,
                       groundMarker, victoryMarker, baseMarker, fitTo, toLatLng};
})();
