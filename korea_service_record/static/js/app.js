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

    /* ----------------------------------------------------------- lightbox -- */

    // Every icon is clickable: full-size art plus the game's own description.
    // The name comes from the page rather than the API, because the page knows
    // the squadron as "39th FIS USAF" while the id alone gives "Squadron 601039".
    async function openLightbox(kind, ident, title) {
        const box = el("lightbox");
        el("lb-title").textContent = title || "";
        el("lb-sub").textContent = "";
        el("lb-desc").textContent = "Loading…";
        el("lb-image").src = "/api/icon/" + kind + "/" + encodeURIComponent(ident);
        el("lb-image").alt = title || "";
        show(box);
        document.body.classList.add("lightbox-open");
        try {
            const d = await getJSON("/api/emblem/" + kind + "/" + encodeURIComponent(ident));
            if (!title) el("lb-title").textContent = d.name;
            const label = { award: "Award", rank: "Rank",
                            squadron: "Squadron" }[kind] || "";
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
            el("lb-desc").textContent = "Could not load details: " + err.message;
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

    /* ------------------------------------------------------------ landing -- */

    function careerCard(career) {
        const stat = (value, label) =>
            '<div class="career-stat"><span class="value">' + esc(value) +
            '</span><span class="label">' + esc(label) + "</span></div>";
        return '<button class="career-card" data-id="' + esc(career.id) + '">' +
            '<div class="career-card-head">' +
                '<span class="career-pilot">' + esc(career.pilot) + "</span>" +
                '<span class="career-rank">' + esc(career.rank) + "</span>" +
            "</div>" +
            '<div class="career-squadron">' + esc(career.squadron) + "</div>" +
            '<div class="career-dates">' + esc(career.start_date) + " &rarr; " +
                esc(career.current_date) + "</div>" +
            '<div class="career-stats">' +
                stat(career.sorties, "Sorties") +
                stat(career.flight_hours, "Hours") +
                stat(career.airborne, "Air") +
                stat(career.ground_targets, "Ground") +
                stat(career.awards, "Awards") +
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
            el("careers-error-text").textContent = "Could not read careers: " + err.message;
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
                    "<span>" + esc(attr.name) + " booster</span>" +
                    "<span>" + points + "</span></div></div>";
            }
            let pips = "";
            for (let i = 0; i < 5; i += 1) {
                pips += '<span class="attr-pip' + (i < attr.level ? " on" : "") + '"></span>';
            }
            return '<div class="attr-row"><div class="attr-head">' +
                "<span>" + esc(attr.name) + "</span>" +
                '<span><span class="attr-value">' + esc(attr.level) + "</span>" +
                points + "</span></div>" +
                '<div class="attr-bar">' + pips + "</div></div>";
        }).join("");
        const note = hasLevels ? "" :
            '<p class="panel-note">Squadron commander &mdash; contributes boosters ' +
            "rather than a simulated skill level.</p>";
        return body + note;
    }

    function awardItem(award) {
        const badge = award.pending ? '<span class="badge pending">pending</span>' : "";
        const when = award.pending
            ? "awaiting award points" : "received " + esc(award.received);
        return '<li class="with-icon">' +
            icon("award", award.type, 88, "award-icon", award.name) +
            "<div>" +
            '<span class="award-name">' + esc(award.name) + badge + "</span>" +
            '<span class="award-dates">earned ' + esc(award.earned) +
            " &middot; " + when + "</span></div></li>";
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
        const detail = entry.detail ? " &mdash; " + esc(entry.detail) : "";
        return '<li class="kind-' + esc(entry.kind) + '">' +
            '<span class="service-date">' + esc(entry.date) + "</span>" +
            '<span class="service-text">' + esc(entry.label) + detail + "</span></li>";
    }

    // Category pictograms, reused from the Great Battles tracker so the two
    // read as one product.
    const CATEGORY_ICON = {
        aircraft: "icon_aircraft", vehicles: "icon_vehicles",
        rail: "icon_railroad", armaments: "icon_armaments",
        buildings: "icon_buildings", naval: "icon_marine"
    };

    function statStrip(items) {
        return items.map((item) => {
            const icon = CATEGORY_ICON[item.key];
            const img = icon
                ? '<img class="stat-icon" src="/static/images/icons/' + icon +
                  '.png" alt="">'
                : "";
            return '<div class="stat-cell">' + img +
                '<span class="stat-value">' + esc(item.value) + "</span>" +
                '<span class="stat-label">' + esc(item.label) + "</span></div>";
        }).join("");
    }

    function breakdown(items) {
        return items.map((item) =>
            '<div class="breakdown-row"><span>' + esc(item.label) + "</span>" +
            "<span>" + esc(item.value) + "</span></div>").join("");
    }

    // One block per sortie: the header the game shows at debrief, then the kill
    // log rebuilt from the timestamped kill events.
    function debriefBlock(d) {
        const flags = [];
        if (d.outcome !== "returned") flags.push("aircraft " + esc(d.outcome));
        if (d.wounded) flags.push("wounded");
        let log = d.log.map((k) => {
            const note = k.parked ? ' <span class="log-note">on the ground</span>' : "";
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
                "<span>+ " + esc(d.scenery) +
                " structures and materiel destroyed</span></div>";
        }
        if (!log) log = '<div class="log-row empty">No confirmed kills.</div>';
        // Take-off, landing and how it ended come from the flight log; the
        // career DB has none of the three.
        const flight = (d.takeoff || d.landing_time)
            ? '<div class="debrief-flight">' +
              (d.takeoff ? "&uarr; " + esc(d.takeoff) + "  " : "") +
              (d.landing_time ? "&darr; " + esc(d.landing_time) : "") +
              (d.landing
                  ? ' <span class="debrief-landing' +
                    (d.landing === "landed" ? "" : " bad") + '">' +
                    esc(d.landing) + "</span>"
                  : "") +
              (d.aircraft ? ' <span class="debrief-plane">' + esc(d.aircraft) +
                            "</span>" : "") +
              "</div>"
            : "";
        return '<article class="debrief"><header class="debrief-head">' +
            '<span class="debrief-no">Mission ' + esc(d.mission_num) + "</span>" +
            '<span class="debrief-date">' + esc(d.date) + " " + esc(d.time) +
                ' <button class="link-btn" data-mission="' + esc(d.mission_id) +
                '">Details</button></span>' +
            "</header>" +
            '<div class="debrief-type">' + esc(d.type) + "</div>" +
            flight +
            '<div class="debrief-meta">' + esc(d.duration) + " &middot; air " +
                esc(d.airborne) + " &middot; ground " + esc(d.ground_targets) +
                (flags.length
                    ? ' &middot; <span class="debrief-flag">' + flags.join(", ") + "</span>"
                    : "") +
            "</div>" +
            '<div class="debrief-log">' + log + "</div></article>";
    }

    function renderRoster() {
        const body = el("d-roster").querySelector("tbody");
        const sorted = rosterRows.slice().sort((a, b) => {
            const x = a[sortKey], y = b[sortKey];
            if (x === null || x === undefined) return 1;
            if (y === null || y === undefined) return -1;
            const cmp = (typeof x === "string")
                ? String(x).localeCompare(String(y))
                : (Number(x) || 0) - (Number(y) || 0);
            return sortAsc ? cmp : -cmp;
        });
        body.innerHTML = sorted.map((p) => {
            const dotClass = ["active", "kia", "wounded", "pow"].indexOf(p.state) >= 0
                ? "status-" + p.state : "status-other";
            const cls = [p.is_player ? "is-player" : "",
                         p.state === "kia" ? "is-kia" : ""].filter(Boolean).join(" ");
            const statusIcon = { kia: "kia", wounded: "wia" }[p.state];
            const statusTitle = p.state +
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
                    (statusIcon
                        ? '<img class="status-icon" src="/static/images/icons/' +
                          statusIcon + '.png" alt="' + esc(p.state) + '">'
                        : '<span class="status-badge ' + dotClass + '"></span>') +
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
                ["Career", d.start_date + " – " + d.current_date],
                ["Sorties", p.sorties + " (" + p.good_sorties + " successful)"],
                ["Flight time", p.flight_time],
                ["Award points", d.award_points]
            ].map((kv) => "<div><dt>" + esc(kv[0]) + "</dt><dd>" +
                          esc(kv[1]) + "</dd></div>").join("");

            const info = [["Rank", p.rank]];
            if (p.birth_date) info.push(["Born", p.birth_date]);
            el("d-info").innerHTML = rows(info.concat([
                ["Squadron", d.squadron],
                ["Status", p.state],
                ["Health", p.health],
                ["Air victories", p.airborne],
                ["Ground targets", p.ground_targets],
                ["Squadron efficiency", d.efficiency]
            ]));
            el("d-attributes").innerHTML = attributeBlock(p.attributes, p.has_levels);

            el("d-incidences").innerHTML = d.incidences.length
                ? d.incidences.map(incidenceItem).join("")
                : '<li class="muted">Nothing recorded.</li>';

            el("d-promotions").innerHTML = d.promotions.length
                ? d.promotions.map(promotionItem).join("")
                : '<li class="muted">None yet.</li>';
            el("d-awards").innerHTML = d.awards.length
                ? d.awards.map(awardItem).join("")
                : '<li class="muted">None yet.</li>';

            el("d-combat-strip").innerHTML = statStrip(d.combat.headline);
            el("d-combat-breakdown").innerHTML = breakdown(d.combat.breakdown);

            const air = d.air_kills_by_type;
            let airHtml = rows(air.airborne.map((a) => [a.name, a.value]));
            if (air.parked.length) {
                airHtml += '<tr><th class="group">Destroyed on the ground</th><td></td></tr>' +
                           rows(air.parked.map((a) => [a.name, a.value]));
            }
            el("d-air-kills").innerHTML = airHtml;

            el("d-missions").innerHTML =
                rows(d.missions_flown.map((m) => [m.label, m.value]));
            el("d-progression").innerHTML = rows([
                ["Starting rank", d.progression.starting_rank],
                ["Current rank", d.progression.current_rank],
                ["Promotions", d.progression.promotions],
                ["Awards", d.progression.awards]
            ]);

            el("d-debrief-count").textContent = "(" + d.debriefings.length + ")";
            el("d-debriefings").innerHTML = d.debriefings.map(debriefBlock).join("");

            el("d-squadron-strip").innerHTML =
                icon("squadron", d.squadron_key, 84, "squadron-emblem strip", d.squadron) +
                statStrip(d.squadron_totals);
            rosterRows = d.roster.map(flatten);
            el("d-roster-count").textContent = "(" + rosterRows.length + ")";
            renderRoster();
            el("d-pending-note").textContent = d.pending_total
                ? d.pending_total + " awards are waiting on award points; you have " +
                  d.award_points + "."
                : "";

            show(el("detail-loading"), false);
            show(el("detail-body"));
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
                "<td>" + esc(f.name) + "</td>" +
                '<td class="num">' + esc(f.airborne) + "</td>" +
                '<td class="num">' + esc(f.ground_targets) + "</td>" +
                '<td class="num">' + esc(f.flight_time) + "</td>" +
                "<td>" + esc(f.outcome) + (f.wounded ? ", wounded" : "") + "</td>" +
                "</tr>").join("");

            const log = m.log.map((k) => {
                const who = k.victim
                    ? ' <span class="log-victim">' + esc(k.victim) + "</span>" : "";
                const alt = k.altitude
                    ? ' <span class="log-alt">' + esc(k.altitude) + " m</span>" : "";
                return '<div class="log-row' + (k.air ? " air" : "") +
                    (k.named ? "" : " scenery") +
                    (k.by_player ? " by-player" : "") + '">' +
                    '<span class="log-time">' + esc(k.time) + "</span>" +
                    "<span>" + esc(k.target) + who + alt + "</span>" +
                    '<span class="log-actor">' + esc(k.actor) + "</span></div>";
            }).join("");

            el("mb-body").innerHTML =
                "<h2>Mission " + esc(m.number) + " &middot; " + esc(m.type) + "</h2>" +
                '<p class="lightbox-sub">' + esc(m.date) + " &middot; " +
                    esc(m.duration) + " &middot; objectives " +
                    esc(m.obj_success) + " met, " + esc(m.obj_failure) + " failed</p>" +
                '<div class="mb-brief">' + brief + "</div>" +
                "<h3>Pilots on this mission</h3>" +
                '<table class="roster mission-roster"><thead><tr>' +
                    "<th></th><th>Rank</th><th>Name</th>" +
                    '<th class="num">Air</th><th class="num">Ground</th>' +
                    '<th class="num">Time</th><th>Outcome</th>' +
                "</tr></thead><tbody>" + flown + "</tbody></table>" +
                "<h3>Combat log <span class=\"count\">(" + m.log.length + ")</span></h3>" +
                '<div class="mb-log">' + log + "</div>";
        } catch (err) {
            el("mb-body").innerHTML =
                '<p class="state-message">Could not open that mission: ' +
                esc(err.message) + "</p>";
        }
    }

    function closeMission() {
        show(el("missionbox"), false);
        document.body.classList.remove("lightbox-open");
    }

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
                            '">Full record &rarr;</a>' +
                    "</div>" +
                "</div>" +
                '<div class="stat-strip pb-strip">' + statStrip(p.combat) + "</div>" +
                '<div class="pb-grid">' +
                    "<div><h3>Characteristics</h3>" +
                        attributeBlock(p.attributes, p.has_levels) + "</div>" +
                    "<div><h3>Missions Flown</h3><table class=\"mini-table\">" +
                        rows(p.missions_flown.map((m) => [m.label, m.value])) +
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
            window.alert("Could not save the photograph: " + err.message);
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

    function route() {
        closePilot();
        closeMission();
        const match = location.hash.match(/^#career\/(.+?)(?:\/pilot\/(\d+))?$/);
        const onDetail = Boolean(match);
        show(el("landing-page"), !onDetail);
        show(el("detail-page"), onDetail);
        show(el("back-btn"), onDetail);
        window.scrollTo(0, 0);
        if (!onDetail) { loadLanding(); return; }
        const careerId = decodeURIComponent(match[1]);
        const pilotId = match[2] ? Number(match[2]) : null;
        el("back-btn").textContent = pilotId
            ? "\u2190 Back to the Career" : "\u2190 Back to Careers";
        loadDetail(careerId, pilotId);
    }

    wirePortrait();
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
            else { sortKey = key; sortAsc = (key === "name" || key === "top_award"); }
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
        const detailsBtn = event.target.closest &&
                           event.target.closest("button[data-mission]");
        if (detailsBtn) {
            openMission(currentCareer, Number(detailsBtn.dataset.mission));
            return;
        }
        const row = event.target.closest && event.target.closest("tr[data-pilot]");
        if (row && !(event.target.closest && event.target.closest("img.emblem"))) {
            openPilot(currentCareer, Number(row.dataset.pilot));
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
    });
    document.addEventListener("keydown", (event) => {
        if (event.key !== "Escape") return;
        if (!el("cropper").hidden) closeCropper();
        else if (!el("missionbox").hidden) closeMission();
        else if (!el("pilotbox").hidden) closePilot();
        else if (!el("lightbox").hidden) closeLightbox();
    });

    window.addEventListener("hashchange", route);
    route();
})();
