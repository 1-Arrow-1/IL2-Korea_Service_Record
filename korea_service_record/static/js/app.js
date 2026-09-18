/**
 * IL-2 Korea Service Record — front end.
 *
 * Two views held in one document: a career list, and the detail for whichever
 * career was clicked. Navigation is by hash so the browser Back button and a
 * page reload both land where the user expects.
 *
 * The detail view follows the Great Battles tracker's three-column service
 * record: who he is on the left, what he did in the middle, mission by mission
 * on the right, and the squadron table across the bottom.
 */

(function () {
    "use strict";

    const el = (id) => document.getElementById(id);
    const show = (node, on = true) => { node.hidden = !on; };

    // Shorthand for the translator. Two languages can be live at once — the
    // chrome in the user's own, a career's record in whatever that record is
    // overridden to — so T() always reads i18n's *current* locale rather than
    // capturing one. Callers set the locale, then render.
    const T = (key, params) => i18n.t(key, params);

    // Rows from the server carry a translation key where one exists and English
    // prose where it does not — a game category name such as "Military
    // Facility" comes out of killStats and has no key of ours.
    const rowLabel = (row) => (row.key ? T(row.key) : row.label);
    const rowValue = (row) => (row.value_key
        ? T(row.value_key, {count: row.value, value: row.value})
        : row.value);

    let settings = {language: "en", languages: []};

    // Escape anything that reaches innerHTML. Pilot names come from the game's
    // own name tables, but they are still third-party strings.
    function esc(value) {
        return String(value === null || value === undefined ? "" : value)
            .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
    }

    const cell = (v) => (v === null || v === undefined) ? "&mdash;" : esc(v);

    // Level with its booster, as the game's own panel shows it: 4 (↑1).
    function levelCell(level, points) {
        if (level === null || level === undefined) {
            return points ? '<span class="boost">↑' + esc(points) + "</span>" : "&mdash;";
        }
        const boost = points
            ? ' <span class="boost">(↑' + esc(points) + ")</span>" : "";
        return esc(level) + boost;
    }

    // Artwork sliced out of the game's own atlases. A missing icon 404s, and
    // onerror hides it so the text beside it simply stands alone.
    const icon = (kind, ident, height, cls, title) =>
        (ident === null || ident === undefined || ident === "")
            ? ""
            : '<img class="' + cls + ' emblem" src="/api/icon/' + kind + "/" +
              encodeURIComponent(ident) + "?h=" + height + '" alt="" title="' +
              esc(title || "") + '" data-kind="' + kind + '" data-id="' +
              esc(ident) + '" data-title="' + esc(title || "") +
              '" onerror="this.style.display=&quot;none&quot;">';

    // The game numbers scheduled missions up from 1 and unscheduled ones -
    // scrambles, urgent tasks - DOWN from -1, in a series of their own. Shown
    // raw that read as "Mission -7" on the forum.
    const missionLabel = (n) => (n < 0)
        ? T("debrief.unscheduled", {number: -n})
        : T("debrief.mission", {number: n});

    /* ----------------------------------------------------------- lightbox -- */

    // Every icon is clickable: full-size art plus the game's own description.
    // The name comes from the page rather than the API, because the page knows
    // the squadron as "39th FIS USAF" while the id alone gives "Squadron 601039".
    async function openLightbox(kind, ident, title) {
        const box = el("lightbox");
        el("lb-title").textContent = title || "";
        el("lb-sub").textContent = "";
        el("lb-desc").textContent = T("common.loading");
        el("lb-image").src = "/api/icon/" + kind + "/" + encodeURIComponent(ident);
        el("lb-image").alt = title || "";
        show(box);
        document.body.classList.add("lightbox-open");
        try {
            const d = await getJSON("/api/emblem/" + kind + "/" + encodeURIComponent(ident));
            if (!title) el("lb-title").textContent = d.name;
            const label = { award: T("awards.awards"), rank: T("pilot.rank"),
                            squadron: T("pilot.squadron") }[kind] || "";
            el("lb-sub").textContent = d.inherited_from
                ? label + " · citation of the " + d.inherited_from
                : label;
            // Descriptions are plain prose with blank-line paragraphs. Build
            // them as text nodes so the game's copy cannot inject markup.
            const desc = el("lb-desc");
            desc.textContent = "";
            const paragraphs = (d.description || "").split(/\n\s*\n/)
                .map((t) => t.trim()).filter(Boolean);
            if (!paragraphs.length) {
                desc.appendChild(document.createTextNode(
                    "No description in the game files."));
            } else {
                paragraphs.forEach((text) => {
                    const node = document.createElement("p");
                    node.textContent = text;
                    desc.appendChild(node);
                });
            }
        } catch (err) {
            el("lb-desc").textContent = T("record.error", {reason: err.message});
        }
    }

    function closeLightbox() {
        show(el("lightbox"), false);
        document.body.classList.remove("lightbox-open");
        el("lb-image").removeAttribute("src");
    }

    const rows = (pairs) => pairs
        .map(([k, v]) => "<tr><th>" + esc(k) + "</th><td>" + esc(v) + "</td></tr>")
        .join("");

    async function getJSON(url) {
        const response = await fetch(url);
        if (!response.ok) throw new Error(response.status + " " + response.statusText);
        return response.json();
    }

    async function postJSON(url, body) {
        const response = await fetch(url, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(body),
        });
        if (!response.ok) throw new Error(response.status + " " + response.statusText);
        return response.json();
    }

    /* ------------------------------------------------------------ landing -- */

    function careerCard(career) {
        const stat = (value, label) =>
            '<div class="career-stat"><span class="value">' + esc(value) +
            '</span><span class="label">' + esc(label) + "</span></div>";
        return '<button class="career-card" data-id="' + esc(career.id) + '">' +
            '<div class="career-card-head">' +
                '<span class="career-pilot">' + esc(career.pilot) + "</span>" +
                (career.flag
                    ? '<img class="career-flag" src="/static/images/flags/' +
                      esc(career.flag) + '.svg" alt="' + esc(career.country_name) +
                      '" title="' + esc(career.country_name) + '">'
                    : "") +
                '<span class="career-rank">' + esc(career.rank) + "</span>" +
            "</div>" +
            '<div class="career-squadron">' + esc(career.squadron) + "</div>" +
            '<div class="career-dates">' + esc(career.start_date) + " &rarr; " +
                esc(career.current_date) + "</div>" +
            '<div class="career-stats">' +
                stat(career.sorties, T("landing.sorties")) +
                stat(career.flight_hours, T("landing.hours")) +
                stat(career.airborne, T("landing.air")) +
                stat(career.ground_targets, T("landing.ground")) +
                stat(career.awards, T("landing.awards")) +
            "</div></button>";
    }

    async function loadLanding() {
        show(el("careers-loading"));
        show(el("careers-list"), false);
        show(el("careers-empty"), false);
        show(el("careers-error"), false);
        try {
            const data = await getJSON("/api/careers");
            show(el("careers-loading"), false);
            if (data.error === "game_not_found") {
                el("careers-error-text").textContent =
                    "No IL-2 Korea installation found. Set KOREA_GAME_DIR and restart.";
                show(el("careers-error"));
                return;
            }
            const careers = data.careers || [];
            if (!careers.length) { show(el("careers-empty")); return; }
            const list = el("careers-list");
            list.innerHTML = careers.map(careerCard).join("");
            list.querySelectorAll(".career-card").forEach((card) => {
                card.addEventListener("click", () => {
                    location.hash = "#career/" + encodeURIComponent(card.dataset.id);
                });
            });
            show(list);
        } catch (err) {
            show(el("careers-loading"), false);
            el("careers-error-text").textContent = T("landing.error", {reason: err.message});
            show(el("careers-error"));
        }
    }

    /* ------------------------------------------------------------- detail -- */

    let rosterRows = [];
    let sortKey = "rank_id";
    let sortAsc = false;

    // Flatten the attribute rows so the table can sort on them like any other
    // column. level is null for the commander; keeping it null means his cell
    // shows a dash and he sorts last rather than as a level-1 pilot.
    function flatten(pilot) {
        const out = Object.assign({}, pilot);
        (pilot.attributes || []).forEach((a) => {
            out[a.name] = a.level;
            out[a.name + "_points"] = a.points;
        });
        return out;
    }

    // The commander has no skill levels — the game shows him boosters only,
    // with no bars. Rendering his zero nibbles as 1/1/1 would be a fiction.
    function attributeBlock(attributes, hasLevels) {
        const body = (attributes || []).map((attr) => {
            const points = '<span class="attr-points">&uarr;' +
                esc(attr.points || 0) + "</span>";
            if (!hasLevels) {
                return '<div class="attr-row booster"><div class="attr-head">' +
                    "<span>" + esc(T("pilot." + attr.name + "_booster")) + "</span>" +
                    "<span>" + points + "</span></div></div>";
            }
            let pips = "";
            for (let i = 0; i < 5; i += 1) {
                pips += '<span class="attr-pip' + (i < attr.level ? " on" : "") + '"></span>';
            }
            return '<div class="attr-row"><div class="attr-head">' +
                "<span>" + esc(T("pilot." + attr.name)) + "</span>" +
                '<span><span class="attr-value">' + esc(attr.level) + "</span>" +
                points + "</span></div>" +
                '<div class="attr-bar">' + pips + "</div></div>";
        }).join("");
        const note = hasLevels ? "" :
            '<p class="panel-note">' + esc(T("pilot.commander_note")) + "</p>";
        return body + note;
    }

    // The ribbon rack: rows of three, highest precedence top-left, a short
    // top row centred, exactly as the bars sit on a tunic. Each ribbon is one
    // image the server composes with its devices; the name is the tooltip.
    function ribbonRows(list, rows, rev) {
        let i = 0;
        return rows.map((n) => {
            const row = list.slice(i, i + n); i += n;
            return '<div class="ribbon-row">' + row.map((r) =>
                '<img class="ribbon' + (r.framed ? " framed" : "") + (r.geometry === "sov" ? " sov" : "") + '" src="/api/ribbon/' + esc(r.type) + "?v=" + esc(rev || 0) +
                '" alt="' + esc(r.name) + '" title="' + esc(r.name) + '" width="168" height="56">').join("") +
                "</div>";
        }).join("");
    }

    // The ribbon rack: rows of three, highest precedence top-left, a short
    // top row centred, exactly as the bars sit on a tunic. Each ribbon is one
    // image the server composes with its devices; the name is the tooltip.
    // Unit citations are worn on the right breast, so they form their own
    // small rack beneath the decorations.
    function ribbonRack(rack) {
        if (!rack) { return ""; }
        const own = rack.ribbons || [], unit = rack.citations || [];
        if (!own.length && !unit.length) { return ""; }
        return (own.length ? '<div class="ribbon-group">' + ribbonRows(own, rack.rows, rack.rev) + "</div>" : "") +
            (unit.length ? '<div class="ribbon-group citations">' +
                ribbonRows(unit, rack.citation_rows, rack.rev) + "</div>" : "");
    }

    // The rack on the coat. The composed ribbons are the same images as the
    // panel's, laid over the photograph at the pocket: ribbons and badge over
    // the wearer's left breast, unit citations over the right.
    let currentRack = null;
    // Service dress (ribbons) or full dress (the medals); remembered per
    // browser, as a convenience only.
    let dress = "service";
    try { dress = localStorage.getItem("tunic_dress") === "full" ? "full" : "service"; } catch (err) { /* private window */ }
    function medalRows(list, rows, rev) {
        // Rows are painted top row last so the pendants of each row hang
        // over the drapes of the row below: the z-index counts down.
        let i = 0;
        return rows.map((n, r) => {
            const row = list.slice(i, i + n); i += n;
            let prev = 0;
            return '<div class="medal-row n' + n + '" style="z-index:' + (rows.length - r) + '">' + row.map((m, k) => {
                let style = "z-index:" + (row.length - k);
                if (m.w) {
                    style += ";width:" + (+m.w).toFixed(3) + "%";
                    if (k > 0 && coatRow.step) { style += ";margin-left:" + (coatRow.step - prev).toFixed(3) + "%"; }
                    if (k > 0 && coatRow.lift) { style += ";margin-top:" + (-k * coatRow.lift).toFixed(3) + "%"; }
                    prev = +m.w;
                }
                return medalImg(m.type, m.name, "medal", rev, style);
            }).join("") + "</div>";
        }).join("");
    }
    function rowsOf(count, per) {
        if (count <= 0) { return []; }
        const first = count % per || per, out = [first];
        for (let n = first; n < count; n += per) { out.push(per); }
        return out;
    }
    function medalImg(id, name, cls, rev, style) {
        return '<img class="' + cls + '"' + (style ? ' style="' + style + '"' : "") +
            ' src="/api/medal/' + esc(id) + "?v=" + esc(rev || 0) +
            '" alt="' + esc(name) + '" title="' + esc(name) + '">';
    }
    // The Soviet-pattern coats lay their awards out in percent of the coat,
    // with widths that come with the pieces. On the common bar one mount
    // starts every `step` percent (they overlap; 0 = mounted touching),
    // each slot `lift` percent higher than the last where the row follows
    // a tilted flap. The pinned orders on the right breast overlap by their
    // own step when there are more than fit the pocket.
    const COAT_ROW = {
        sov: {step: 5.69, lift: 0, pinned: 8.6},
        dprk: {step: 0, lift: 0, pinned: 6.9},
    };
    let coatRow = COAT_ROW.sov;
    function openTunic(name) {
        const rack = currentRack;
        if (!rack || !rack.tunic) { return; }
        const coat = rack.tunic, full = dress === "full";
        const own = rack.ribbons || [], unit = rack.citations || [];
        el("tunic-title").textContent = name || "";
        document.querySelectorAll(".dress-btn").forEach((b) => {
            b.classList.toggle("active", b.dataset.dress === dress);
            b.setAttribute("aria-pressed", b.dataset.dress === dress ? "true" : "false");
        });
        const tunic = el("tunic");
        tunic.dataset.coat = coat;
        tunic.classList.toggle("full", full);
        el("tunic-coat").src = "/static/images/tunic_" + coat + ".jpg";
        // The lapel and collar cut-outs belong to the USAF coat's photograph.
        show(el("tunic-lapel"), coat === "usaf");
        show(el("tunic-collar"), coat === "usaf");
        el("tunic-neck").innerHTML = full && rack.neck
            ? '<img class="neck-medal" src="' + esc(rack.neck_src) + '" alt="' + esc(rack.neck_name) + '" title="' + esc(rack.neck_name) + '">' : "";
        let right = "", left = "", caption;
        if (coat === "sov" || coat === "dprk") {
            coatRow = COAT_ROW[coat];
            // 1943 rules. Left breast (viewer's right): the Hero's star in
            // kind above everything, then the mounted orders and medals -
            // or their ribbon bars in service dress. Right breast: wound
            // stripes on top, the class badge, then the screw-back orders,
            // which have no ribbon; in service dress their bars went on the
            // right side too.
            const pinnedIds = new Set((rack.pinned || []).map((p) => p.type));
            // A slot is placed on the coat in percent of the coat, sized to
            // its piece, and the piece fills it.
            const piece = (cls, m, extra) => '<div class="' + cls + '" style="width:' + (+m.w).toFixed(3) + '%">' +
                medalImg(m.type, m.name, "sov-piece", rack.medal_rev, "width:100%") + "</div>";
            const hero = rack.hero ? medalImg(rack.hero.type, rack.hero.name, "tunic-hero", rack.medal_rev, "width:" + (+rack.hero.w).toFixed(3) + "%") : "";
            // The right breast is a stack over the pocket: wound stripes on
            // top (1942 order: 8-10 mm above the awards, side by side), the
            // class badge below them (1950 order), the orders - or their
            // bars - at the bottom; with nothing below, a badge takes the
            // orders' place, as the orders said.
            let stack = "";
            const stripes = rack.stripes || [];
            if (stripes.length) {
                const total = stripes.reduce((a, m) => a + +m.w, 0) + 1 * (stripes.length - 1);
                stack += '<div class="sov-stripes" style="width:' + total.toFixed(3) + '%">' + stripes.map((m) =>
                    medalImg(m.type, m.name, "sov-piece", rack.medal_rev, "width:" + (+m.w / total * 100).toFixed(3) + "%")).join("") + "</div>";
            }
            if (rack.wings) { stack += piece("sov-wings", rack.wings); }
            if (full) {
                const bar = rack.medals || [];
                right = '<div class="sov-breast">' + hero + (bar.length ? '<div class="medal-group">' + medalRows(bar, rack.medal_rows, rack.medal_rev) + "</div>" : "") + "</div>";
                // One row from the centre outward, overlapping when wider
                // than the pocket, the senior on top.
                let prevW = 0;
                if ((rack.pinned || []).length) {
                    stack += '<div class="pinned-row">' + rack.pinned.map((m, k) => {
                        const style = "z-index:" + (99 - k) + ";width:" + (+m.w).toFixed(3) + "%" +
                            (k > 0 ? ";margin-right:" + (coatRow.pinned - prevW).toFixed(3) + "%" : "");
                        prevW = +m.w;
                        return medalImg(m.type, m.name, "pinned", rack.medal_rev, style);
                    }).join("") + "</div>";
                }
            } else {
                const bars = own.filter((r) => !pinnedIds.has(r.type) && !(rack.hero && r.type === rack.hero.type));
                const rightBars = own.filter((r) => pinnedIds.has(r.type));
                right = '<div class="sov-breast">' + hero + (bars.length ? '<div class="ribbon-group">' + ribbonRows(bars, rowsOf(bars.length, 3), rack.rev) + "</div>" : "") + "</div>";
                if (rightBars.length) {
                    stack += '<div class="sov-bars"><div class="ribbon-group">' + ribbonRows(rightBars, rowsOf(rightBars.length, 3), rack.rev) + "</div></div>";
                }
            }
            left = stack ? '<div class="sov-right">' + stack + "</div>" : "";
            caption = T("awards.tunic_caption_" + coat + (full ? "_full" : ""));
        } else {
            const badge = rack.badge ? '<img class="tunic-badge" src="/api/icon/award/' + esc(rack.badge) + '" alt="' + esc(rack.badge_name) + '" title="' + esc(rack.badge_name) + '">' : "";
            if (full) {
                const bar = rack.medals || [];
                right = badge + (bar.length ? '<div class="medal-group">' + medalRows(bar, rack.medal_rows, rack.medal_rev) + "</div>" : "");
            } else {
                // Regulations allowed four ribbons per row; a man with four
                // rows of three would push his wings into the collar, so on
                // the coat a large rack goes four across (the panel keeps three).
                const wide = own.length > 9;
                const rows = wide ? rowsOf(own.length, 4) : rack.rows;
                right = badge + (own.length ? '<div class="ribbon-group' + (wide ? " four" : "") + '">' + ribbonRows(own, rows, rack.rev) + "</div>" : "");
            }
            left = unit.length ? '<div class="ribbon-group">' + ribbonRows(unit, rack.citation_rows, rack.rev) + "</div>" : "";
            caption = T(full ? "awards.tunic_caption_full" : "awards.tunic_caption");
        }
        el("tunic-right").innerHTML = right;
        el("tunic-left").innerHTML = left;
        el("tunic-caption").textContent = caption;
        show(el("tunicbox"), true);
        document.body.classList.add("lightbox-open");
    }
    function closeTunic() {
        show(el("tunicbox"), false);
        document.body.classList.remove("lightbox-open");
    }

    function awardItem(award) {
        const badge = award.pending ? '<span class="badge pending">pending</span>' : "";
        const when = award.pending
            ? T("awards.awaiting_points")
            : T("awards.received", {date: award.received});
        const history = award.history || [];
        // A cluster replaces the decoration below it, so the earlier rungs are
        // folded under the ribbon the pilot wears now; a chevron unfolds them.
        const toggle = history.length
            ? '<button type="button" class="history-toggle" aria-expanded="false" ' +
              'title="' + esc(T("awards.history", {count: history.length})) + '">' +
              '<span class="sr-only">' + esc(T("awards.history", {count: history.length})) + "</span>" +
              '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 6l4 4 4-4"/></svg></button>'
            : "";
        const folded = history.length
            ? '<ol class="award-history" hidden>' + history.map(function (h) {
                return '<li class="with-icon">' +
                    icon("award", h.type, 56, "award-icon small", h.name) +
                    "<div>" +
                    '<span class="award-name">' + esc(h.name) + "</span>" +
                    '<span class="award-dates">' + esc(T("awards.earned", {date: h.earned})) +
                    " &middot; " + esc(T("awards.received", {date: h.received})) + "</span></div></li>";
            }).join("") + "</ol>"
            : "";
        return '<li class="with-icon' + (history.length ? " has-history" : "") + '">' +
            icon("award", award.type, 88, "award-icon", award.name) +
            "<div>" +
            '<span class="award-name">' + esc(award.name) + badge + "</span>" +
            '<span class="award-dates">' + esc(T("awards.earned", {date: award.earned})) +
            " &middot; " + when + "</span></div>" + toggle + folded + "</li>";
    }

    function promotionItem(promotion) {
        const badge = promotion.pending ? '<span class="badge pending">pending</span>' : "";
        return '<li class="with-icon">' +
            icon("rank", promotion.rank_key, 56, "rank-icon", promotion.rank) +
            "<div>" +
            '<span class="award-name">' + esc(promotion.rank) + badge + "</span>" +
            '<span class="award-dates">' + esc(promotion.date) + "</span></div></li>";
    }

    function incidenceItem(entry) {
        const detailText = entry.detail_key
            ? T(entry.detail_key, {value: entry.detail_value})
            : entry.detail;
        const detail = detailText ? " &mdash; " + esc(detailText) : "";
        return '<li class="kind-' + esc(entry.kind) + '">' +
            '<span class="service-date">' + esc(entry.date) + "</span>" +
            '<span class="service-text">' + esc(rowLabel(entry)) + detail +
            "</span></li>";
    }

    // Category pictograms, reused from the Great Battles tracker so the two
    // read as one product.
    const CATEGORY_ICON = {
        aircraft: "icon_aircraft", vehicles: "icon_vehicles",
        rail: "icon_railroad", armaments: "icon_armaments",
        buildings: "icon_buildings", naval: "icon_marine"
    };

    // Line glyphs in the style of the category pictograms (a ring, ink
    // strokes), drawn inline so they take the page's own ink and stay crisp.
    const RING = '<circle cx="32" cy="32" r="29"/>';
    const PLANE = '<path class="fill" d="M32 11l2.4 14.5L51 33.5v4l-16-3.2-1.2 11.2 6.4 4v3L32 50.6l-8.2 1.9v-3l6.4-4L29 34.3l-16 3.2v-4l16.6-8z"/>';
    const AIRCRAFT_ICON = {
        serviceable: RING + PLANE,
        repair: RING + '<path class="fill" d="M44.5 17.5a9 9 0 0 0-10.3 12L18 45.7a3.4 3.4 0 0 0 4.8 4.8l16.2-16.2a9 9 0 0 0 12-10.3l-5.6 5.6-5.2-1.2-1.2-5.2z"/>',
        reserve: RING + '<path d="M14 47V32a18 18 0 0 1 36 0v15M22 47V37h20v10M14 47h36"/>',
        received: RING + '<path d="M32 12v14m-6-5l6 6 6-6"/><path d="M17 30h30v18H17zM17 36h30"/>',
        written_off: RING + '<g class="dim">' + PLANE + '</g><path class="bad" d="M17 47L47 17"/>',
        incoming: '<path d="M12 22h24v14H12zM36 27h8l6 6v3h-14z"/><circle cx="19" cy="41" r="3"/><circle cx="43" cy="41" r="3"/>',
        stores: '<path d="M20 16h24v32H20zM20 26h24M20 38h24"/>',
        wrench: '<path class="fill" d="M44.5 17.5a9 9 0 0 0-10.3 12L18 45.7a3.4 3.4 0 0 0 4.8 4.8l16.2-16.2a9 9 0 0 0 12-10.3l-5.6 5.6-5.2-1.2-1.2-5.2z"/>'
    };
    const glyph = (name, cls) =>
        '<svg class="' + (cls || "stat-icon") + ' glyph" viewBox="0 0 64 64" aria-hidden="true">' +
        AIRCRAFT_ICON[name] + "</svg>";

    function statStrip(items) {
        return items.map((item) => {
            const icon = CATEGORY_ICON[item.key];
            const img = icon
                ? '<img class="stat-icon" src="/static/images/icons/' + icon +
                  '.png" alt="">'
                : item.glyph ? glyph(item.glyph) : "";
            return '<div class="stat-cell">' + img +
                '<span class="stat-value">' + esc(item.value) + "</span>" +
                '<span class="stat-label">' +
                esc(item.key ? T("combat." + item.key) : item.label) + "</span></div>";
        }).join("");
    }

    /* ------------------------------------------------------ operations map -- */

    // One Leaflet map for the career page, rebuilt per career; the layers
    // are swapped as the toggles change so the tiles never reload.
    let opsMap = null;
    let opsLayers = {};
    let opsData = null;

    async function renderOpsMap(careerId, subjectId, subjectName, isPlayer) {
        const panel = el("d-map-panel");
        const box = el("d-map");
        if (!window.L || !window.KoreaMap) { panel.hidden = true; return; }
        panel.hidden = false;
        el("d-map-whose").textContent = "";
        if (!opsMap) {
            opsMap = KoreaMap.createMap(box);
            ["routes", "victories", "losses", "targets", "labels"].forEach((name) => {
                el("map-" + name).addEventListener("change", applyOpsLayers);
            });
        }
        Object.values(opsLayers).forEach((layer) => opsMap.removeLayer(layer));
        opsLayers = {};
        try {
            const [data, features] = await Promise.all([
                getJSON("/api/map/" + encodeURIComponent(careerId)),
                KoreaMap.overlayFeatures()
            ]);
            opsData = data;
            opsLayers.labels = KoreaMap.labelLayer(features);
            opsLayers.routes = L.layerGroup(data.routes.map((r) => KoreaMap.routeLayer(r, true, T)));
            opsLayers.targets = L.layerGroup(data.routes.map((r) => KoreaMap.targetMarker(r.target, true, r, T)).filter(Boolean));
            // The subject's own victories drawn on top of the squadron's, so
            // his page shows where he fought amid where the unit did.
            opsLayers.victories = L.layerGroup(data.victories.map((v) => {
                const m = KoreaMap.victoryMarker(v, T);
                if (subjectId != null && v.pilot_id === subjectId) m.options.className += " mine";
                return m;
            }));
            opsLayers.losses = KoreaMap.lossLayer(data.losses, T);
            opsLayers.bases = L.layerGroup(data.bases.map((b) => KoreaMap.baseMarker(b, T)));
            el("d-map-count").textContent =
                "(" + T("map.count", {sorties: data.routes.length, victories: data.victories.length}) + ")";
            applyOpsLayers();
            opsMap.invalidateSize();
            KoreaMap.fitTo(opsMap, [opsLayers.routes, opsLayers.victories], 0.08);
        } catch (err) {
            console.error("map", err);
            panel.hidden = true;
        }
    }

    function applyOpsLayers() {
        if (!opsMap) return;
        const want = {
            routes: el("map-routes").checked, victories: el("map-victories").checked,
            losses: el("map-losses").checked,
            targets: el("map-targets").checked, labels: el("map-labels").checked, bases: true
        };
        Object.keys(opsLayers).forEach((name) => {
            const on = opsMap.hasLayer(opsLayers[name]);
            if (want[name] && !on) opsLayers[name].addTo(opsMap);
            if (!want[name] && on) opsMap.removeLayer(opsLayers[name]);
        });
    }

    // The mission's own map in the modal: the briefed route with numbered
    // turning points, the target, and every kill where it fell.
    let missionMap = null;
    let missionMapId = 0;
    function renderMissionMap(m, careerId) {
        const box = el("mb-map");
        if (!box || !window.L || !window.KoreaMap) return;
        if (missionMap) { missionMap.remove(); missionMap = null; }
        if (!m.route || !m.route.length) { box.hidden = true; return; }
        box.hidden = false;
        // Buttons and double-click zoom; not the wheel, which scrolls the modal.
        missionMap = KoreaMap.createMap(box, {scrollWheelZoom: false});
        const route = KoreaMap.routeLayer({points: m.route.map((p) => [p.x, p.z, p.type])}, false, T).addTo(missionMap);
        const target = KoreaMap.targetMarker(m.target, false);
        if (target) target.addTo(missionMap);
        const kills = L.layerGroup((m.log || []).filter((k) => k.x || k.z).map((k) => {
            if (k.air) {
                return KoreaMap.victoryMarker({x: k.x, z: k.z, alt: k.altitude, target: k.target,
                    victim: k.victim, pilot: k.actor, number: m.number, date: m.date, mission_id: m.id}, T);
            }
            return KoreaMap.groundMarker(k, T);
        })).addTo(missionMap);
        KoreaMap.overlayFeatures().then((features) => {
            if (missionMap) KoreaMap.labelLayer(features).addTo(missionMap);
        });
        missionMap.invalidateSize();
        KoreaMap.fitTo(missionMap, [route, kills], 0.12);
        // The flown track and our losses come separately: they are read
        // from the flight log, and the modal is up before that is done.
        const mapId = ++missionMapId;
        const legend = el("mb-legend");
        if (legend) legend.hidden = true;
        if (!careerId) return;
        getJSON("/api/track/" + encodeURIComponent(careerId) + "/" + m.id).then((track) => {
            if (!missionMap || mapId !== missionMapId) return;
            const layers = [];
            if (track.segments && track.segments.length) {
                layers.push(KoreaMap.trackLayer(track, T).addTo(missionMap));
            }
            if (track.losses && track.losses.length) {
                layers.push(KoreaMap.lossLayer(track.losses, T).addTo(missionMap));
            }
            if (legend) {
                const items = [["route", T("map.legend_route")]];
                if (track.segments && track.segments.length) {
                    items.push(["track", T("map.track")]);
                    if (track.segments.some((s) => s.warp)) items.push(["warp", T("map.warp")]);
                }
                if ((track.marks || []).some((k) => k.kind === "hit")) items.push(["hit", T("map.hits")]);
                if (track.losses && track.losses.length) items.push(["loss", T("map.losses")]);
                legend.innerHTML = items.map(([cls, label]) =>
                    '<span class="legend-item"><i class="legend-' + cls + '"></i>' + esc(label) + "</span>").join("");
                legend.hidden = false;
            }
            if (layers.length) KoreaMap.fitTo(missionMap, [route, kills].concat(layers), 0.12);
        }).catch((err) => console.error("track", err));
    }

    // The squadron's aircraft: strength, the repair queue with the game's own
    // completion dates, deliveries on their way, and the three stores.
    function renderAircraft(a) {
        const panel = el("d-aircraft-panel");
        if (!a || !a.on_strength) { panel.hidden = true; return; }
        panel.hidden = false;
        panel.querySelectorAll(".h-glyph").forEach((span) => {
            span.innerHTML = glyph(span.dataset.glyph, "h-icon");
        });
        el("d-aircraft-count").textContent =
            "(" + T("aircraft.on_strength", {count: a.on_strength, type: a.type}) + ")";
        el("d-aircraft-strip").innerHTML = statStrip([
            {label: T("aircraft.serviceable"), value: a.serviceable, glyph: "serviceable"},
            {label: T("aircraft.in_repair"), value: a.in_repair, glyph: "repair"},
            {label: T("aircraft.reserve"), value: a.reserve, glyph: "reserve"},
            {label: T("aircraft.received"), value: a.received, glyph: "received"},
            {label: T("aircraft.written_off"), value: a.written_off, glyph: "written_off"}
        ]);

        const when = (days) => days === 0 ? T("aircraft.today")
            : days === 1 ? T("aircraft.tomorrow")
            : T("aircraft.in_days", {days: days});
        // Same shape as the Incoming list: the day it is due back on the
        // left, the airframe and its condition as the text.
        el("d-aircraft-repairs").innerHTML = a.repairs.map((r) =>
            '<li><span class="service-date">' + esc(r.ready) + "</span>" +
            '<span class="service-text">' +
            esc(r.code ? r.code + " " + r.type : T("aircraft.airframe", {slot: r.slot + 1, type: r.type})) + " " +
            '<span class="repair-health"><span class="bar"><span style="width:' + r.health + '%"></span></span>' +
            esc(T("aircraft.health", {health: r.health})) + "</span>" +
            (r.ready ? " &middot; " + esc(when(r.days)) : "") +
            "</span></li>").join("");
        el("d-aircraft-repairs-note").textContent =
            a.repairs.length ? "" : T("aircraft.none_in_repair");

        // Quantities in the units the game's Resources screen prints: fuel
        // in litres, ordnance and equipment in "units", the rest plain.
        const qty = (kind, n) => kind === "fuel" ? T("aircraft.litres", {value: n.toLocaleString()})
            : (kind === "ordnance" || kind === "equipment")
                ? T("aircraft.units", {value: n.toLocaleString()})
                : n.toLocaleString();
        // One line per delivery on its way, in the game's own resource
        // names: aircraft, pilots, fuel, ordnance, equipment.
        el("d-aircraft-arrivals").innerHTML = a.arrivals.map((x) =>
            '<li><span class="service-date">' + esc(x.date) + "</span>" +
            '<span class="service-text">' +
            esc(T("aircraft.arrival_" + x.kind,
                  {quantity: qty(x.kind, x.quantity), type: x.type})) +
            " · " + esc(when(x.days)) + "</span></li>").join("");
        el("d-aircraft-arrivals-note").textContent = a.arrivals.length ? ""
            : a.last_delivery
                ? T("aircraft.none_on_order_last", a.last_delivery)
                : T("aircraft.none_on_order");

        el("d-aircraft-stores").innerHTML = rows([
            [T("aircraft.fuel"), qty("fuel", a.stores.fuel)],
            [T("aircraft.ordnance"), qty("ordnance", a.stores.ordnance)],
            [T("aircraft.equipment"), qty("equipment", a.stores.equipment)],
            [T("aircraft.requests"), a.stores.requests]
        ]);

        // Every airframe the squadron has had, line-up first, write-offs
        // last. Folded by default: forty rows are for the reader who wants
        // them, not for everyone scrolling to the roster.
        const frames = a.airframes || [];
        el("d-airframes-count").textContent = "(" + frames.length + ")";
        el("d-airframes").querySelector("tbody").innerHTML = frames.map((f) => {
            const status = f.status === "repair" && f.ready
                ? T("aircraft.status_repair_until", {date: f.ready})
                : T("aircraft.status_" + f.status);
            const usual = f.usual
                ? '<button class="link-btn pilot-link" data-pilot="' + f.usual.id + '">' +
                  esc(f.usual.name) + "</button>" +
                  ' <span class="muted">(' + esc(f.usual.sorties) + ")</span>"
                : "—";
            const fate = f.lost
                ? esc(f.lost.date) + (f.lost.pilot ? " · " + esc(f.lost.pilot) : "")
                : "";
            return '<tr class="is-' + esc(f.status) + '">' +
                '<td class="code-cell">' + esc(f.code || "—") +
                    (f.number ? ' <span class="muted">' +
                        esc(T("debrief.airframe", {number: f.number})) + "</span>" : "") + "</td>" +
                "<td>" + esc(status) + "</td>" +
                "<td>" + esc(f.since) + "</td>" +
                '<td class="num">' + esc(f.sorties) + "</td>" +
                "<td>" + usual + "</td>" +
                '<td class="num">' + esc(f.pilots) + "</td>" +
                '<td class="num">' + esc(f.airborne) + "</td>" +
                '<td class="num">' + esc(f.ground_targets) + "</td>" +
                '<td class="num">' + esc(f.repairs) + "</td>" +
                '<td class="fate-cell">' + fate + "</td></tr>";
        }).join("");
    }

    function breakdown(items) {
        return items.map((item) =>
            '<div class="breakdown-row"><span>' + esc(rowLabel(item)) + "</span>" +
            "<span>" + esc(item.value) + "</span></div>").join("");
    }

    // The airframe flown, what hung under it, the fuel and the range - from
    // the mission's manifest. Guns-only sorties say so rather than nothing.
    function loadoutLine(d) {
        const parts = [];
        if (d.airframe) parts.push(d.airframe);
        parts.push(d.loadout || T("debrief.guns_only"));
        if (d.fuel_pct != null) parts.push(T("debrief.fuel", {percent: d.fuel_pct}));
        if (d.range_km) parts.push(T("debrief.range", {km: d.range_km}));
        if (!d.loadout && d.fuel_pct == null) return "";
        return '<div class="debrief-loadout">' + parts.map(esc).join(" &middot; ") + "</div>";
    }

    // One block per sortie: the header the game shows at debrief, then the kill
    // log rebuilt from the timestamped kill events.
    function debriefBlock(d) {
        const flags = [];
        if (d.outcome !== "returned") {
            flags.push(T("debrief.aircraft_state",
                         {state: T("debrief.outcome_" + d.outcome)}));
        }
        if (d.wounded) flags.push(T("debrief.wounded"));
        if (d.assists) flags.push(T("debrief.assists", {count: d.assists}));
        if (d.friendly_kills) flags.push(T("debrief.friendly_kills", {count: d.friendly_kills}));
        let log = d.log.map((k) => {
            if (k.hurt) {
                // Damage taken, in the same timeline as the kills so the
                // sortie reads in the order it happened.
                // The attacker is shown only where the log recorded one —
                // most of what hits a career pilot is flak the log leaves
                // anonymous, and "by unknown" on every line is noise.
                const byWhom = k.hurt.self_inflicted
                    ? T("debrief.own_ordnance") : k.hurt.attacker;
                const by = byWhom
                    ? ' <span class="hurt-by">' + esc(byWhom) + "</span>"
                    : "";
                return '<div class="log-row hurt">' +
                    '<span class="log-time">' + esc(k.time) + "</span>" +
                    "<span>" + esc(T("debrief.hit_burst", {hits: k.hurt.hits})) +
                    by + ' <span class="hurt-total">' +
                    esc(T("debrief.hit_total", {total: k.hurt.total})) +
                    "</span></span></div>";
            }
            const note = k.parked
                ? ' <span class="log-note">' + esc(T("debrief.on_the_ground")) + "</span>" : "";
            const who = k.victim
                ? ' <span class="log-victim">' + esc(k.victim) + "</span>" : "";
            const alt = k.altitude
                ? ' <span class="log-alt">' + esc(k.altitude) + " m</span>" : "";
            return '<div class="log-row' + (k.air ? " air" : "") + '">' +
                '<span class="log-time">' + esc(k.time) + "</span>" +
                "<span>" + esc(k.target) + who + note + alt + "</span></div>";
        }).join("");
        if (d.scenery) {
            log += '<div class="log-row scenery"><span class="log-time"></span>' +
                "<span>" + esc(T("debrief.more_destroyed", {count: d.scenery})) +
                "</span></div>";
        }
        if (!log) log = '<div class="log-row empty">' +
            esc(T("debrief.no_kills")) + "</div>";
        // Take-off, landing and how it ended come from the flight log; the
        // career DB has none of the three.
        const flight = (d.takeoff || d.landing_time)
            ? '<div class="debrief-flight">' +
              (d.takeoff ? "&uarr; " + esc(d.takeoff) + "  " : "") +
              (d.landing_time ? "&darr; " + esc(d.landing_time) : "") +
              (d.landing
                  ? ' <span class="debrief-landing' +
                    (d.landing_key === "landed" ? "" : " bad") + '">' +
                    esc(T("debrief." + d.landing_key)) + "</span>"
                  : "") +
              (d.aircraft ? ' <span class="debrief-plane">' + esc(d.aircraft) +
                            "</span>" : "") +
              "</div>"
            : "";
        return '<article class="debrief"><header class="debrief-head">' +
            '<span class="debrief-no">' +
                esc(missionLabel(d.mission_num)) + "</span>" +
            '<span class="debrief-date">' + esc(d.date) + " " + esc(d.time) +
                ' <button class="link-btn" data-mission="' + esc(d.mission_id) +
                '">' + esc(T("debrief.details")) + "</button></span>" +
            "</header>" +
            '<div class="debrief-type">' + esc(d.type) + "</div>" +
            flight +
            loadoutLine(d) +
            '<div class="debrief-meta">' +
                esc(T("debrief.summary", {duration: d.duration, air: d.airborne,
                                          ground: d.ground_targets})) +
                (flags.length
                    ? ' &middot; <span class="debrief-flag">' + flags.join(", ") + "</span>"
                    : "") +
            "</div>" +
            '<div class="debrief-log">' + log + "</div></article>";
    }

    // A stamp squared up to the pixel looks printed, not pressed, so each is
    // tilted. The angle is derived from the pilot's id rather than drawn at
    // random: Math.random() would give every row a fresh angle on each sort,
    // and the whole column would twitch each time a heading was clicked.
    const STAMPED = ["active", "wounded", "kia", "missing"];

    function stampAngle(seed) {
        let h = 0;
        const text = String(seed);
        for (let i = 0; i < text.length; i += 1) {
            h = (h * 31 + text.charCodeAt(i)) | 0;
        }
        return (Math.abs(h) % 25) - 12;      // -12deg .. +12deg
    }

    // Sorting on status: the line-up, then the wounded who will rejoin it,
    // then the pool, then the gone. Alphabetical put "reserve" between the
    // missing and the wounded, which separates nothing.
    const STATE_ORDER = { active: 0, not_ready: 1, wounded: 2, reserve: 3, missing: 4, kia: 5 };

    function renderRoster() {
        const body = el("d-roster").querySelector("tbody");
        const sorted = rosterRows.slice().sort((a, b) => {
            let x = a[sortKey], y = b[sortKey];
            if (sortKey === "top_award") { x = a.top_award_rank; y = b.top_award_rank; }
            if (sortKey === "state") {
                x = STATE_ORDER[x] ?? 9;
                y = STATE_ORDER[y] ?? 9;
            }
            if (x === null || x === undefined) return 1;
            if (y === null || y === undefined) return -1;
            const cmp = (typeof x === "string")
                ? String(x).localeCompare(String(y))
                : (Number(x) || 0) - (Number(y) || 0);
            return sortAsc ? cmp : -cmp;
        });
        body.innerHTML = sorted.map((p) => {
            const dotClass = ["active", "kia", "missing", "wounded", "reserve", "not_ready", "pow"]
                .indexOf(p.state) >= 0 ? "status-" + p.state : "status-other";
            // The missing are greyed with the dead: both are gone for good and
            // neither is coming back, whatever the difference on paper.
            const cls = [p.is_player ? "is-player" : "",
                         (p.state === "kia" || p.state === "missing")
                             ? "is-kia" : "",
                         p.reserve ? "is-reserve" : ""].filter(Boolean).join(" ");
            const statusIcon = { kia: "kia", wounded: "wia" }[p.state];
            // Translated where a key exists; an unmapped state keeps its raw
            // "state N" so the number reaches the screenshot.
            const stateWord = i18n.has("state." + p.state)
                ? T("state." + p.state) : p.state;
            const statusTitle = stateWord +
                (p.state_until ? " until " + p.state_until : "") +
                (p.state_since ? " " + p.state_since : "");
            return '<tr class="' + cls + '" data-pilot="' + p.id + '">' +
                '<td class="photo-cell"><img class="roster-photo" src="' +
                    photoUrl(currentCareer, p.id, p.avatar, 162) +
                    '" alt="" onerror="this.style.display=&quot;none&quot;"></td>' +
                '<td class="rank-cell">' +
                    (icon("rank", p.rank_key, 56, "rank-icon", p.rank) ||
                     esc(p.rank)) + "</td>" +
                "<td>" + esc(p.name) + "</td>" +
                '<td class="award-cell col-award">' +
                    (icon("award", p.top_award_id, 88, "award-icon", p.top_award) ||
                     "&mdash;") + "</td>" +
                '<td class="col-status" title="' + esc(statusTitle) + '">' +
                    (STAMPED.indexOf(p.state) >= 0
                        ? '<img class="status-stamp" src="/static/images/stamps/' +
                          esc(p.state) + '.png" alt="' + esc(p.state) +
                          '" style="transform:rotate(' + stampAngle(p.id) + 'deg)">'
                        // No stamp drawn for this state: say it in words. A
                        // bare dot was invisible in a forum screenshot, and
                        // a roster with blank status cells reads as broken.
                        : '<span class="status-word ' + dotClass + '">' +
                          esc(stateWord) + "</span>") +
                    "</td>" +
                '<td class="num">' + esc(p.airborne) + "</td>" +
                '<td class="num">' + esc(p.ground_targets) + "</td>" +
                '<td class="num">' + esc(p.sorties) + "</td>" +
                '<td class="num">' + esc(p.flight_hours) + "</td>" +
                '<td class="num">' + levelCell(p.skills, p.skills_points) + "</td>" +
                '<td class="num">' + levelCell(p.discipline, p.discipline_points) + "</td>" +
                '<td class="num">' + levelCell(p.courage, p.courage_points) + "</td>" +
                '<td class="num">' + esc(p.awards_held) + "</td>" +
                '<td class="num">' + (p.awards_pending ? esc(p.awards_pending) : "") + "</td>" +
                "</tr>";
        }).join("");
        el("d-roster").querySelectorAll("th").forEach((th) => {
            th.classList.toggle("sorted", th.dataset.sort === sortKey);
            th.classList.toggle("asc", th.dataset.sort === sortKey && sortAsc);
        });
    }

    async function loadDetail(careerId, pilotId) {
        show(el("detail-loading"));
        show(el("detail-body"), false);
        try {
            const d = await getJSON("/api/career/" + encodeURIComponent(careerId) +
                                    (pilotId ? "?pilot=" + pilotId : ""));
            // The server already resolved which language this record belongs
            // in — global, or this career's override — and rendered the game's
            // own names accordingly. The labels have to follow, so the locale
            // is switched before anything is drawn.
            await i18n.setLocale(d.language || settings.language);
            const p = d.player;

            currentCareer = d.id;
            currentPilot = d.subject_id;
            currentAvatar = p.avatar;
            showPortrait(currentCareer, currentPilot, p.avatar);

            el("d-name").textContent = p.name;
            el("d-subtitle").innerHTML =
                icon("rank", p.rank_key, 56, "rank-icon", p.rank) +
                "<span>" + esc(p.rank) + " · " + esc(d.squadron) + "</span>" +
                icon("squadron", d.squadron_key, 96, "squadron-emblem", d.squadron);
            el("d-meta").innerHTML = [
                [T("record.career"), d.start_date + " – " + d.current_date],
                [T("record.sorties"), T("record.sorties_value",
                    {total: p.sorties, good: p.good_sorties})],
                [T("record.flight_time"), p.flight_time],
                [T("record.award_points"), d.award_points]
            ].map((kv) => "<div><dt>" + esc(kv[0]) + "</dt><dd>" +
                          esc(kv[1]) + "</dd></div>").join("");

            const info = [[T("pilot.rank"), p.rank]];
            if (p.birth_date) info.push([T("pilot.born"), p.birth_date]);
            el("d-info").innerHTML = rows(info.concat([
                [T("pilot.squadron"), d.squadron],
                [T("pilot.status"), T("state." + p.state)],
                [T("pilot.health"), p.health],
                [T("pilot.air_victories"), p.airborne],
                [T("pilot.ground_targets"), p.ground_targets],
                [T("pilot.squadron_efficiency"), d.efficiency]
            ]));
            el("d-attributes").innerHTML = attributeBlock(p.attributes, p.has_levels);

            el("d-incidences").innerHTML = d.incidences.length
                ? d.incidences.map(incidenceItem).join("")
                : '<li class="muted">' + esc(T("incidences.none")) + "</li>";

            // Hours written into the career: the clock follows, no choice offered.
            const sw = el("corrected-times");
            sw.disabled = Boolean(d.corrections_applied);
            if (d.corrections_applied) { sw.checked = true; }
            el("corrected-switch").title = T(d.corrections_applied ? "app.corrected_applied" : "app.corrected_hint");
            el("corrected-switch").classList.toggle("locked", Boolean(d.corrections_applied));

            const rackEl = el("d-ribbon-rack");
            rackEl.innerHTML = ribbonRack(d.ribbon_rack);
            rackEl.hidden = !rackEl.innerHTML;
            rackEl.setAttribute("aria-label", T("awards.ribbon_rack"));
            currentRack = d.ribbon_rack;
            // The flight record opens on its own page, ready to print.
            const logbook = el("d-logbook");
            logbook.href = "/logbook?career=" + encodeURIComponent(careerId) +
                (d.player && d.player.id != null ? "&pilot=" + encodeURIComponent(d.player.id) : "");
            logbook.title = T("logbook.open_hint");
            logbook.hidden = false;
            rackEl.classList.toggle("wearable", Boolean(d.ribbon_rack && d.ribbon_rack.tunic));
            rackEl.title = d.ribbon_rack && d.ribbon_rack.tunic ? T("awards.tunic_hint") : "";
            rackEl.onclick = () => openTunic(d.player ? d.player.name : "");

            el("d-promotions").innerHTML = d.promotions.length
                ? d.promotions.map(promotionItem).join("")
                : '<li class="muted">' + esc(T("awards.none_yet")) + "</li>";
            el("d-awards").innerHTML = d.awards.length
                ? d.awards.map(awardItem).join("")
                : '<li class="muted">' + esc(T("awards.none_yet")) + "</li>";

            el("d-combat-strip").innerHTML = statStrip(d.combat.headline);
            el("d-combat-breakdown").innerHTML = breakdown(d.combat.breakdown);

            const air = d.air_kills_by_type;
            let airHtml = rows(air.airborne.map((a) => [a.name, a.value]));
            if (air.parked.length) {
                airHtml += '<tr><th class="group">' +
                    esc(T("combat.destroyed_on_ground")) + "</th><td></td></tr>" +
                           rows(air.parked.map((a) => [a.name, a.value]));
            }
            el("d-air-kills").innerHTML = airHtml;

            el("d-missions").innerHTML =
                rows(d.missions_flown.map((m) => [rowLabel(m), m.value]));
            el("d-progression").innerHTML = rows([
                [T("progression.starting_rank"), d.progression.starting_rank],
                [T("progression.current_rank"), d.progression.current_rank],
                [T("progression.promotions"), d.progression.promotions],
                [T("progression.awards"), d.progression.awards]
            ]);

            el("d-debrief-count").textContent = "(" + d.debriefings.length + ")";
            el("d-debriefings").innerHTML = d.debriefings.map(debriefBlock).join("");

            el("d-squadron-strip").innerHTML =
                icon("squadron", d.squadron_key, 84, "squadron-emblem strip", d.squadron) +
                statStrip(d.squadron_totals);
            renderAircraft(d.aircraft);
            // Decorations to the unit itself. Hidden entirely when there are
            // none: an empty "Unit Citations" heading would be a promise.
            const citations = d.citations || [];
            const strip = el("d-squadron-citations");
            strip.hidden = citations.length === 0;
            // One row per ladder (DUC and its clusters, then the ROK PUC and
            // its clusters), every rung the unit has held, oldest first.
            strip.innerHTML = citations.length === 0 ? "" :
                '<span class="citation-label">' + T("roster.citations") + "</span>" +
                citations.map((ladder) =>
                    '<div class="citation-row">' + (ladder.awards || []).map((c) =>
                        '<span class="citation' + (c.current ? " current" : " retired") + '">' +
                        icon("award", c.type, 64, "award-icon citation-icon", c.name) +
                        '<span class="citation-text"><span class="award-name">' +
                        esc(c.name) + '</span><span class="award-dates">' +
                        esc(T("awards.received", {date: c.received})) +
                        "</span></span></span>").join("") + "</div>").join("");
            // The header art is whatever the squadron flies. Set as a custom
        // property so the CSS keeps ownership of size, opacity and blending,
        // and an aircraft with no picture yet simply shows nothing.
        const head = document.querySelector(".record-head");
        if (head) {
            head.style.setProperty("--plane-art", d.plane
                ? 'url("/static/images/planes/' + d.plane + '.png")'
                : "none");
            head.style.setProperty("--classification", d.classification
                ? 'url("/static/images/stamps/' + d.classification + '.png")'
                : "none");
        }
        // The seal across the photograph's corner. Shown only once the image
        // has actually loaded, so a nation whose seal is not drawn yet gets a
        // clean photograph rather than a broken-image icon over the face.
        const seal = el("d-portrait-seal");
        currentSeal = d.seal || "";
        if (seal) {
            seal.hidden = true;
            if (d.seal) {
                seal.onload = () => { seal.hidden = false; };
                seal.onerror = () => { seal.hidden = true; };
                seal.src = "/static/images/stamps/seal_" + d.seal + ".png";
            }
        }

        // Combat efficiency and the victory roll. Both panels are hidden
        // outright when a pilot has nothing to put in them — an AI wingman
        // with no air kills should not get an empty "Confirmed Victories".
        // A figure is more useful next to the sortie that produced it, so the
        // rows that name one open that debrief; the hint explains where a
        // number comes from, which matters most for the score, which is the
        // game's own and counts nothing recognisable.
        el("d-performance").innerHTML = (d.performance || []).map((row) => {
            const hint = row.hint_key ? T(row.hint_key) : "";
            const linked = row.mission_id !== null && row.mission_id !== undefined;
            return '<tr class="perf-row' + (linked ? " linked" : "") + '"' +
                (linked ? ' data-mission="' + esc(row.mission_id) + '"' : "") +
                (hint ? ' title="' + esc(hint) + '"' : "") + ">" +
                "<th>" + esc(rowLabel(row)) + "</th><td>" + esc(rowValue(row)) +
                (linked && row.mission_num
                    ? ' <span class="perf-mission">' +
                      esc(missionLabel(row.mission_num)) + "</span>"
                    : "") +
                "</td></tr>";
        }).join("");
        show(el("d-performance-panel"), (d.performance || []).length > 0);

        const victories = d.victories || [];
        el("d-victory-count").textContent = victories.length
            ? "(" + victories.length + ")" : "";
        // Whose. A forum reader "took a minute to figure out" that the roll
        // was the commander's and not the squadron's — the roster below it
        // lists forty other men.
        el("d-victory-whose").textContent = d.player
            ? "— " + [d.player.rank, d.player.name].filter(Boolean).join(" ")
            : "";
        el("d-victories").innerHTML = victories.map((v) =>
            '<div class="victory" data-mission="' + esc(v.mission_id) + '">' +
                '<span class="victory-no">' + esc(v.number) + "</span>" +
                "<span>" +
                    '<span class="victory-type">' + esc(v.type) + "</span>" +
                    (v.victim
                        ? ' <span class="victory-victim">' + esc(v.victim) + "</span>"
                        : "") +
                    '<span class="victory-when">' + esc(v.date) + " &middot; " +
                        esc(v.time) + "</span>" +
                "</span>" +
                '<span class="victory-alt">' +
                    (v.altitude ? esc(v.altitude) + " m" : "") + "</span>" +
            "</div>").join("");
        show(el("d-victories-panel"), victories.length > 0);

        rosterRows = d.roster.map(flatten);
            // "(66)" hid that 47 of them were in the pool. Say both.
            const inReserve = rosterRows.filter((p) => p.reserve).length;
            el("d-roster-count").textContent = inReserve
                ? "(" + T("roster.count_with_reserve",
                          {total: rosterRows.length, reserve: inReserve}) + ")"
                : "(" + rosterRows.length + ")";
            renderRoster();
            el("d-pending-note").textContent = d.pending_total
                ? T("awards.pending_note", {count: d.pending_total,
                                            points: d.award_points})
                : "";

            fillPicker(el("career-lang-select"), d.language_override || "", true);
            i18n.apply(el("detail-page"));
            show(el("detail-loading"), false);
            show(el("detail-body"));
            // After the body is visible: Leaflet needs the box to have a size.
            renderOpsMap(d.id, d.subject_id, p.name, d.is_player);
        } catch (err) {
            el("detail-loading").innerHTML =
                '<p class="state-message">Could not open that career: ' +
                esc(err.message) + "</p>";
        }
    }

    /* ----------------------------------------------------- mission modal -- */

    // The game's briefing is a fragment of HTML. Rather than trust it, tags are
    // stripped and the text rebuilt as paragraphs — the copy is the game's, but
    // it still ends up on the page.
    function briefingParagraphs(raw) {
        const text = String(raw || "")
            .replace(/<\s*br\s*\/?>/gi, "\n")
            .replace(/<\/(h1|h2|p|div)>/gi, "\n\n")
            .replace(/<[^>]*>/g, "")
            .replace(/&nbsp;/gi, " ");
        return text.split(/\n\s*\n/).map((t) => t.trim()).filter(Boolean);
    }

    async function openMission(careerId, missionId) {
        const box = el("missionbox");
        el("mb-body").innerHTML = '<p class="state-message">Loading\u2026</p>';
        show(box);
        document.body.classList.add("lightbox-open");
        try {
            const m = await getJSON("/api/mission/" + encodeURIComponent(careerId) +
                                    "/" + missionId);
            const brief = briefingParagraphs(m.briefing)
                .map((t) => "<p>" + esc(t) + "</p>").join("") ||
                '<p class="muted">No briefing recorded.</p>';

            const flown = m.flown.map((f) =>
                '<tr' + (f.is_player ? ' class="is-player"' : "") + ">" +
                '<td class="photo-cell"><img class="roster-photo small" src="' +
                    photoUrl(careerId, f.pilot_id, f.avatar, 120) +
                    '" alt="" onerror="this.style.display=&quot;none&quot;"></td>' +
                "<td>" + icon("rank", f.rank_key, 26, "rank-icon", f.rank) + "</td>" +
                // Name with the airframe and loadout beneath it: one column
                // rather than two, so the table fits a modal at any width.
                '<td class="name-cell">' + esc(f.name) +
                    '<span class="loadout-line">' +
                    (f.airframe ? '<span class="airframe-no">' + esc(f.airframe) + "</span> · " : "") +
                    // Each store stays on one line; the cell breaks between them.
                    (f.loadout ? f.loadout.split(", ").map((s) =>
                        '<span class="store">' + esc(s) + "</span>").join(", ")
                        : esc(T("debrief.guns_only"))) + "</span></td>" +
                '<td class="num">' + esc(f.airborne) + "</td>" +
                '<td class="num">' + esc(f.ground_targets) + "</td>" +
                '<td class="num">' + esc(f.flight_time) + "</td>" +
                "<td>" + esc(T("debrief.outcome_" + f.outcome)) +
                    (f.wounded ? ", " + esc(T("debrief.wounded")) : "") +
                    (f.assists ? ", " + esc(T("debrief.assists", {count: f.assists})) : "") +
                    (f.friendly_kills ? ', <span class="pilot-hurt">' +
                        esc(T("debrief.friendly_kills", {count: f.friendly_kills})) + "</span>" : "") +
                "</td>" +
                // The timeline hangs off the cell rather than expanding the
                // table: eight pilots each with their own burst list would
                // bury the flight it is meant to summarise.
                '<td class="num damage-cell' +
                    ((f.damage_log || []).length ? " has-log" : "") + '"' +
                    ((f.damage_log || []).length
                        ? ' title="' + esc(f.damage_log.map((b) =>
                            b.time + "  " + T("debrief.hit_burst", {hits: b.hits}) +
                            (b.self_inflicted ? " — " + T("debrief.own_ordnance")
                                : b.attacker ? " — " + b.attacker : "") +
                            "  → " + b.total + "%").join("\n")) + '"'
                        : "") + ">" +
                    (f.plane_damage === null || f.plane_damage === undefined
                        ? "&mdash;"
                        : esc(f.plane_damage > 0 ? f.plane_damage + "%"
                                                 : T("debrief.damage_tiny")) +
                          (f.pilot_damage
                              ? ' <span class="pilot-hurt">' +
                                esc(T("debrief.pilot_hurt", {percent: f.pilot_damage})) +
                                "</span>"
                              : "")) +
                "</td>" +
                "</tr>").join("");

            const log = m.log.map((k) => {
                const who = k.victim
                    ? ' <span class="log-victim">' + esc(k.victim) + "</span>" : "";
                const alt = k.altitude
                    ? ' <span class="log-alt">' + esc(k.altitude) + " m</span>" : "";
                const many = k.count > 1
                    ? ' <span class="log-count">×' + k.count + "</span>" : "";
                return '<div class="log-row' + (k.air ? " air" : "") +
                    (k.named ? "" : " scenery") +
                    (k.by_player ? " by-player" : "") + '">' +
                    '<span class="log-time">' + esc(k.time) + "</span>" +
                    "<span>" + esc(k.target) + many + who + alt + "</span>" +
                    '<span class="log-actor">' + esc(k.actor) + "</span></div>";
            }).join("");

            el("mb-body").innerHTML =
                "<h2>" + esc(missionLabel(m.number)) +
                    " &middot; " + esc(m.type) + "</h2>" +
                '<p class="lightbox-sub">' + esc(m.date) + " &middot; " +
                    esc(m.duration) + " &middot; " +
                    esc(T("debrief.objectives", {met: m.obj_success,
                                                 failed: m.obj_failure})) + "</p>" +
                '<div class="mb-brief">' + brief + "</div>" +
                '<div id="mb-map" class="map-view mission"></div>' +
                '<div id="mb-legend" class="map-legend" hidden></div>' +
                "<h3>" + esc(T("debrief.pilots_on_mission")) + "</h3>" +
                '<div class="table-scroll"><table class="roster mission-roster"><thead><tr>' +
                    "<th></th><th>" + esc(T("debrief.rank")) + "</th><th>" +
                    esc(T("debrief.name")) + "</th>" +
                    '<th class="num">' + esc(T("debrief.air")) + '</th>' +
                    '<th class="num">' + esc(T("debrief.ground")) + '</th>' +
                    '<th class="num">' + esc(T("debrief.time")) + "</th><th>" +
                    esc(T("debrief.outcome")) + "</th>" +
                    '<th class="num">' + esc(T("debrief.damage")) + "</th>" +
                "</tr></thead><tbody>" + flown + "</tbody></table></div>" +
                "<h3>" + esc(T("debrief.combat_log")) +
                    ' <span class="count">(' + m.log.length + ")</span></h3>" +
                '<div class="mb-log">' + log + "</div>";
            renderMissionMap(m, careerId);
        } catch (err) {
            el("mb-body").innerHTML =
                '<p class="state-message">Could not open that mission: ' +
                esc(err.message) + "</p>";
        }
    }

    function closeMission() {
        show(el("missionbox"), false);
        document.body.classList.remove("lightbox-open");
        if (missionMap) { missionMap.remove(); missionMap = null; }
    }

    // A route or a victory on the operations map opens its debriefing.
    document.addEventListener("map:mission", (event) => {
        if (currentCareer) openMission(currentCareer, Number(event.detail));
    });

    /* ------------------------------------------------------- pilot modal -- */

    // A modal rather than a page: the roster is 46 rows and the point is to
    // check two or three pilots without losing your place. The full record is
    // one click further on, and renders through the same code the player's
    // page uses.
    async function openPilot(careerId, pilotId) {
        const box = el("pilotbox");
        el("pb-body").innerHTML = '<p class="state-message">Loading\u2026</p>';
        show(box);
        document.body.classList.add("lightbox-open");
        try {
            const p = await getJSON("/api/pilot/" + encodeURIComponent(careerId) +
                                    "/" + pilotId);
            const status = p.state +
                (p.state_until ? " until " + p.state_until : "") +
                (p.state_since ? ", " + p.state_since : "");
            const awards = p.awards_list.length
                ? p.awards_list.map((a) =>
                    icon("award", a.type, 56, "award-icon", a.name)).join("")
                : '<span class="muted">No awards yet.</span>';
            const promos = p.promotions_list.length
                ? p.promotions_list.map((r) =>
                    icon("rank", r.rank_key, 34, "rank-icon", r.rank)).join("")
                : '<span class="muted">No promotions.</span>';
            const recent = p.recent.length
                ? p.recent.map((d) =>
                    '<div class="pb-sortie"><span>' + esc(d.date) + "</span><span>" +
                    esc(d.type) + '</span><span class="num">' + esc(d.airborne) +
                    " air</span></div>").join("")
                : '<span class="muted">No sorties flown.</span>';

            el("pb-body").innerHTML =
                '<div class="pb-head">' +
                    '<div class="portrait-frame small">' +
                        '<div class="portrait"><img src="' +
                            photoUrl(careerId, p.id, p.avatar, 392) + '" alt=""></div>' +
                        '<img class="portrait-overlay" src="/static/images/photo-frame.svg" alt="">' +
                        (currentSeal
                            ? '<img class="portrait-seal" alt="" src="/static/images/stamps/seal_' +
                              esc(currentSeal) + '.png" onerror="this.hidden=true">'
                            : "") +
                    "</div>" +
                    '<div class="pb-identity">' +
                        '<h2 id="pb-name">' + esc(p.name) + "</h2>" +
                        '<p class="pb-rank">' +
                            icon("rank", p.rank_key, 34, "rank-icon", p.rank) +
                            "<span>" + esc(p.rank) + " \u00b7 " + esc(p.squadron) +
                            "</span></p>" +
                        '<p class="pb-status">' + esc(status) + "</p>" +
                        '<a class="nav-btn small" href="#career/' +
                            encodeURIComponent(careerId) + "/pilot/" + p.id +
                            '">Full record &rarr;</a> ' +
                        '<a class="nav-btn small" target="_blank" rel="noopener" href="/logbook?career=' +
                            encodeURIComponent(careerId) + "&pilot=" + p.id + '" title="' + esc(T("logbook.open_hint")) + '">' +
                            esc(T("logbook.open")) + "</a>" +
                    "</div>" +
                "</div>" +
                (ribbonRack(p.ribbon_rack)
                    ? '<div class="ribbon-rack pb-rack" aria-label="' + esc(T("awards.ribbon_rack")) + '">' +
                      ribbonRack(p.ribbon_rack) + "</div>"
                    : "") +
                '<div class="stat-strip pb-strip">' + statStrip(p.combat) + "</div>" +
                '<div class="pb-grid">' +
                    "<div><h3>Characteristics</h3>" +
                        attributeBlock(p.attributes, p.has_levels) + "</div>" +
                    "<div><h3>Missions Flown</h3><table class=\"mini-table\">" +
                        rows(p.missions_flown.map((m) => [rowLabel(m), m.value])) +
                        "</table></div>" +
                "</div>" +
                "<h3>Promotions</h3><div class=\"pb-emblems\">" + promos + "</div>" +
                "<h3>Awards</h3><div class=\"pb-emblems\">" + awards + "</div>" +
                "<h3>Recent Sorties</h3><div class=\"pb-sorties\">" + recent + "</div>";
        } catch (err) {
            el("pb-body").innerHTML =
                '<p class="state-message">Could not open that pilot: ' +
                esc(err.message) + "</p>";
        }
    }

    function closePilot() {
        show(el("pilotbox"), false);
        document.body.classList.remove("lightbox-open");
    }

    /* -------------------------------------------------------- portraits -- */

    // Photographs are the user's own files, kept outside the game install. The
    // crop happens here in a canvas and the server stores the finished PNG, so
    // what lands on disk is exactly what was on screen when Save was pressed.
    const PORTRAIT_W = 360;
    const PORTRAIT_H = 450;

    let currentCareer = "";
    let currentPilot = null;
    let currentAvatar = "";
    // The nation's photo seal, remembered from the career so the pilot modal
    // can strike it across its own portrait — every pilot in a squadron is
    // filed under the same seal.
    let currentSeal = "";
    const crop = { image: null, scale: 1, minScale: 1, x: 0, y: 0,
                   dragging: false, lastX: 0, lastY: 0 };

    // One URL for every portrait. The endpoint serves the user's upload if
    // there is one and falls back to the portrait the game ships for that
    // pilot, so all 46 have a face without anybody uploading anything.
    function photoUrl(careerId, pilotId, avatar, height, bust) {
        let url = "/api/photo/" + encodeURIComponent(careerId) + "/" + pilotId +
                  "?avatar=" + encodeURIComponent(avatar || "");
        if (height) url += "&h=" + height;
        if (bust) url += "&t=" + Date.now();
        return url;
    }

    function showPortrait(careerId, pilotId, avatar) {
        const box = el("d-portrait");
        const img = new Image();
        img.onload = () => {
            box.innerHTML = "";
            box.appendChild(img);
            show(el("photo-clear"));
        };
        img.onerror = () => {
            box.innerHTML = "<span class=\"portrait-empty\">No photograph</span>";
            show(el("photo-clear"), false);
        };
        img.alt = "";
        img.src = photoUrl(careerId, pilotId, avatar, 490, true);
    }

    function drawCrop() {
        const canvas = el("crop-canvas");
        const ctx = canvas.getContext("2d");
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        if (!crop.image) return;
        const w = crop.image.width * crop.scale;
        const h = crop.image.height * crop.scale;
        // Keep the frame covered: no empty margins whatever the user drags.
        crop.x = Math.min(0, Math.max(canvas.width - w, crop.x));
        crop.y = Math.min(0, Math.max(canvas.height - h, crop.y));
        ctx.drawImage(crop.image, crop.x, crop.y, w, h);
    }

    function openCropper(file) {
        const reader = new FileReader();
        reader.onload = () => {
            const img = new Image();
            img.onload = () => {
                crop.image = img;
                crop.minScale = Math.max(PORTRAIT_W / img.width,
                                         PORTRAIT_H / img.height);
                crop.scale = crop.minScale;
                crop.x = (PORTRAIT_W - img.width * crop.scale) / 2;
                crop.y = (PORTRAIT_H - img.height * crop.scale) / 2;
                el("crop-zoom").value = 100;
                show(el("cropper"));
                document.body.classList.add("lightbox-open");
                drawCrop();
            };
            img.onerror = () => window.alert("That file could not be read as an image.");
            img.src = reader.result;
        };
        reader.readAsDataURL(file);
    }

    function closeCropper() {
        show(el("cropper"), false);
        document.body.classList.remove("lightbox-open");
        crop.image = null;
    }

    async function saveCrop() {
        const canvas = el("crop-canvas");
        const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
        if (!blob) return;
        try {
            const response = await fetch(
                "/api/photo/" + encodeURIComponent(currentCareer) + "/" + currentPilot,
                { method: "PUT", body: blob });
            const result = await response.json();
            if (result.error) throw new Error(result.error);
            closeCropper();
            showPortrait(currentCareer, currentPilot, currentAvatar);
        } catch (err) {
            window.alert(T("photo.save_failed", {reason: err.message}));
        }
    }

    function wirePortrait() {
        el("photo-pick").addEventListener("click", () => el("photo-file").click());
        el("photo-file").addEventListener("change", (event) => {
            const file = event.target.files && event.target.files[0];
            if (file) openCropper(file);
            event.target.value = "";
        });
        el("photo-clear").addEventListener("click", async () => {
            await fetch("/api/photo/" + encodeURIComponent(currentCareer) + "/" +
                        currentPilot, { method: "DELETE" });
            showPortrait(currentCareer, currentPilot, currentAvatar);
        });
        el("crop-save").addEventListener("click", saveCrop);
        document.addEventListener("click", (event) => {
            if (event.target.closest && event.target.closest("[data-crop-close]")) {
                closeCropper();
            }
        });

        const canvas = el("crop-canvas");
        canvas.addEventListener("pointerdown", (event) => {
            crop.dragging = true;
            crop.lastX = event.clientX;
            crop.lastY = event.clientY;
            canvas.classList.add("dragging");
            canvas.setPointerCapture(event.pointerId);
        });
        canvas.addEventListener("pointermove", (event) => {
            if (!crop.dragging) return;
            crop.x += event.clientX - crop.lastX;
            crop.y += event.clientY - crop.lastY;
            crop.lastX = event.clientX;
            crop.lastY = event.clientY;
            drawCrop();
        });
        const stop = () => { crop.dragging = false; canvas.classList.remove("dragging"); };
        canvas.addEventListener("pointerup", stop);
        canvas.addEventListener("pointercancel", stop);
        canvas.addEventListener("wheel", (event) => {
            event.preventDefault();
            const slider = el("crop-zoom");
            slider.value = Math.min(400, Math.max(100,
                Number(slider.value) - Math.sign(event.deltaY) * 10));
            slider.dispatchEvent(new Event("input"));
        }, { passive: false });

        el("crop-zoom").addEventListener("input", (event) => {
            if (!crop.image) return;
            // Zoom about the frame centre so the subject does not drift.
            const canvasEl = el("crop-canvas");
            const cx = canvasEl.width / 2, cy = canvasEl.height / 2;
            const next = crop.minScale * (Number(event.target.value) / 100);
            const ratio = next / crop.scale;
            crop.x = cx - (cx - crop.x) * ratio;
            crop.y = cy - (cy - crop.y) * ratio;
            crop.scale = next;
            drawCrop();
        });
    }

    /* --------------------------------------------------------- navigation -- */

    /* ---------------------------------------------------------- language -- */

    function fillPicker(select, current, withDefault) {
        const options = withDefault
            ? ['<option value="">' + esc(T("app.language_default")) + "</option>"]
            : [];
        settings.languages.forEach((lang) => {
            options.push('<option value="' + esc(lang.code) + '"' +
                (lang.code === current ? " selected" : "") + ">" +
                esc(lang.name) + "</option>");
        });
        select.innerHTML = options.join("");
        if (withDefault && !current) select.value = "";
    }

    // The chrome is always in the global language. The detail page may not be,
    // so it is translated separately, after its own locale is set.
    async function applyChrome() {
        await i18n.setLocale(settings.language);
        i18n.apply(document);
        fillPicker(el("lang-select"), settings.language, false);
        el("corrected-times").checked = Boolean(settings.corrected_times);
    }

    // The missions the player warped through, re-timed to the plan (the
    // Career Helper computes them; see corrections.py). A view switch: the
    // career file is never touched, so it can be flipped at any time.
    async function changeCorrectedTimes(on) {
        settings = await postJSON("/api/settings", {corrected_times: on});
        el("corrected-times").checked = Boolean(settings.corrected_times);
        route();
    }

    async function changeLanguage(code) {
        settings = await postJSON("/api/settings", {language: code});
        await applyChrome();
        route();
    }

    async function changeCareerLanguage(code) {
        if (!currentCareer) return;
        await postJSON("/api/settings/career/" + encodeURIComponent(currentCareer),
                       {language: code});
        loadDetail(currentCareer, currentPilot);
    }

    function route() {
        closePilot();
        closeMission();
        const match = location.hash.match(/^#career\/(.+?)(?:\/pilot\/(\d+))?$/);
        const onDetail = Boolean(match);
        show(el("landing-page"), !onDetail);
        show(el("detail-page"), onDetail);
        show(el("back-btn"), onDetail);
        el("quit-btn").title = T("app.quit_hint");
        el("helper-btn").title = T("app.helper_hint");
        window.scrollTo(0, 0);
        if (!onDetail) {
            el("corrected-times").disabled = false;
            el("corrected-times").checked = Boolean(settings.corrected_times);
            el("corrected-switch").classList.remove("locked");
            i18n.setLocale(settings.language).then(() => {
                i18n.apply(document);
                loadLanding();
            });
            return;
        }
        const careerId = decodeURIComponent(match[1]);
        const pilotId = match[2] ? Number(match[2]) : null;
        el("back-btn").innerHTML = "← <span>" + esc(T("app.back")) + "</span>";
        loadDetail(careerId, pilotId);
    }

    wirePortrait();
    // Closing the tab does not stop the server; this does, the same way
    // the tray's Quit does, after a confirmation so a stray click cannot
    // kill the session. The page then explains itself, since every later
    // request would fail.
    el("quit-btn").addEventListener("click", async () => {
        if (!window.confirm(T("app.quit_confirm"))) { return; }
        try {
            const r = await fetch("/api/quit", {method: "POST"});
            if (!r.ok) { throw new Error(String(r.status)); }
            document.body.innerHTML = '<main class="page-container"><p class="state-message closed">' +
                esc(T("app.quit_done")) + "</p></main>";
        } catch (err) {
            window.alert(T("app.quit_failed"));
        }
    });

    el("back-btn").addEventListener("click", () => {
        // From a pilot's record, step back to the career rather than all the
        // way out to the career list.
        const match = location.hash.match(/^#career\/(.+?)\/pilot\/\d+$/);
        location.hash = match ? "#career/" + match[1] : "";
    });
    el("d-roster").querySelectorAll("th").forEach((th) => {
        th.addEventListener("click", () => {
            const key = th.dataset.sort;
            if (!key) return;
            if (key === sortKey) sortAsc = !sortAsc;
            else { sortKey = key; sortAsc = (key === "name"); }
            renderRoster();
        });
    });

    // One delegated listener: icons are rebuilt on every render, so binding
    // per element would leak handlers.
    document.addEventListener("click", (event) => {
        if (event.target.closest && event.target.closest("[data-pilot-close]")) {
            closePilot();
            return;
        }
        if (event.target.closest && event.target.closest("[data-mission-close]")) {
            closeMission();
            return;
        }
        // Any element carrying data-mission opens that debrief: the Details
        // button, and a row of the victory roll, which is the natural way to
        // ask "what else happened that sortie".
        const detailsBtn = event.target.closest &&
                           event.target.closest("[data-mission]");
        if (detailsBtn) {
            openMission(currentCareer, Number(detailsBtn.dataset.mission));
            return;
        }
        // A roster row, or a pilot's name in the airframe table.
        const row = event.target.closest &&
                    event.target.closest("tr[data-pilot], button[data-pilot]");
        if (row && !(event.target.closest && event.target.closest("img.emblem"))) {
            openPilot(currentCareer, Number(row.dataset.pilot));
            return;
        }
        const toggle = event.target.closest && event.target.closest("button.history-toggle");
        if (toggle) {
            const open = toggle.getAttribute("aria-expanded") !== "true";
            toggle.setAttribute("aria-expanded", open ? "true" : "false");
            const list = toggle.parentElement.querySelector("ol.award-history");
            if (list) { list.hidden = !open; }
            return;
        }
        const img = event.target.closest && event.target.closest("img.emblem");
        if (img) {
            openLightbox(img.dataset.kind, img.dataset.id, img.dataset.title);
            return;
        }
        if (event.target.closest && event.target.closest("[data-close]")) {
            closeLightbox();
        }
        if (event.target.closest && event.target.closest("[data-tunic-close]")) {
            closeTunic();
        }
        const dressBtn = event.target.closest && event.target.closest(".dress-btn");
        if (dressBtn && dressBtn.dataset.dress !== dress) {
            dress = dressBtn.dataset.dress;
            try { localStorage.setItem("tunic_dress", dress); } catch (err) { /* not persisted */ }
            openTunic(el("tunic-title").textContent);
        }
    });
    document.addEventListener("keydown", (event) => {
        if (event.key !== "Escape") return;
        if (!el("tunicbox").hidden) { closeTunic(); return; }
        if (!el("cropper").hidden) closeCropper();
        else if (!el("missionbox").hidden) closeMission();
        else if (!el("pilotbox").hidden) closePilot();
        else if (!el("lightbox").hidden) closeLightbox();
    });

    el("lang-select").addEventListener("change", (event) => {
        changeLanguage(event.target.value);
    });
    el("corrected-times").addEventListener("change", (event) => {
        changeCorrectedTimes(event.target.checked);
    });
    // The Career Helper is a separate desktop program; the button only shows
    // where one is installed beside the tracker (or the script, from source).
    getJSON("/api/helper").then((h) => { show(el("helper-btn"), Boolean(h && h.available)); }).catch(() => {});
    el("helper-btn").addEventListener("click", async () => {
        try { await fetch("/api/helper", {method: "POST"}); } catch (err) { /* the server said why in its log */ }
    });
    el("career-lang-select").addEventListener("change", (event) => {
        changeCareerLanguage(event.target.value);
    });

    window.addEventListener("hashchange", route);

    // Nothing renders until the strings are in: a first paint in English that
    // then flips to German is worse than a few hundred milliseconds of blank.
    (async function boot() {
        try {
            settings = await getJSON("/api/settings");
        } catch (err) {
            console.warn("[app] settings unavailable, staying with English", err);
        }
        await i18n.init(settings.language);
        await applyChrome();
        route();
    })();
})();
