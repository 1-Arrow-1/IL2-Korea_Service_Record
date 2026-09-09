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
            : '<img class="' + cls + '" src="/api/icon/' + kind + "/" +
              encodeURIComponent(ident) + "?h=" + height + '" alt="" title="' +
              esc(title || "") + '" onerror="this.style.display=&quot;none&quot;">';

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
            icon("award", award.type, 44, "award-icon", award.name) +
            "<div>" +
            '<span class="award-name">' + esc(award.name) + badge + "</span>" +
            '<span class="award-dates">earned ' + esc(award.earned) +
            " &middot; " + when + "</span></div></li>";
    }

    function promotionItem(promotion) {
        const badge = promotion.pending ? '<span class="badge pending">pending</span>' : "";
        return '<li class="with-icon">' +
            icon("rank", promotion.rank_key, 26, "rank-icon", promotion.rank) +
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
            return '<div class="log-row' + (k.air ? " air" : "") + '">' +
                '<span class="log-time">' + esc(k.time) + "</span>" +
                "<span>" + esc(k.target) + note + "</span></div>";
        }).join("");
        if (d.scenery) {
            log += '<div class="log-row scenery"><span class="log-time"></span>' +
                "<span>+ " + esc(d.scenery) +
                " structures and materiel destroyed</span></div>";
        }
        if (!log) log = '<div class="log-row empty">No confirmed kills.</div>';
        return '<article class="debrief"><header class="debrief-head">' +
            '<span class="debrief-no">Mission ' + esc(d.mission_num) + "</span>" +
            '<span class="debrief-date">' + esc(d.date) + " " + esc(d.time) + "</span>" +
            "</header>" +
            '<div class="debrief-type">' + esc(d.type) + "</div>" +
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
            return '<tr class="' + cls + '">' +
                '<td class="rank-cell">' +
                    (icon("rank", p.rank_key, 22, "rank-icon", p.rank) ||
                     esc(p.rank)) + "</td>" +
                "<td>" + esc(p.name) + "</td>" +
                '<td class="award-cell">' +
                    (icon("award", p.top_award_id, 40, "award-icon", p.top_award) ||
                     "&mdash;") + "</td>" +
                '<td><span class="status-dot ' + dotClass + '"></span>' + esc(p.state) +
                    (p.state_until
                        ? ' <span class="until">until ' + esc(p.state_until) + "</span>"
                        : "") + "</td>" +
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

    async function loadDetail(careerId) {
        show(el("detail-loading"));
        show(el("detail-body"), false);
        try {
            const d = await getJSON("/api/career/" + encodeURIComponent(careerId));
            const p = d.player;

            el("d-name").textContent = p.name;
            el("d-subtitle").innerHTML =
                icon("rank", p.rank_key, 26, "rank-icon", p.rank) +
                "<span>" + esc(p.rank) + " · " + esc(d.squadron) + "</span>" +
                icon("squadron", d.squadron_key, 64, "squadron-emblem", d.squadron);
            el("d-meta").innerHTML = [
                ["Career", d.start_date + " – " + d.current_date],
                ["Sorties", p.sorties + " (" + p.good_sorties + " successful)"],
                ["Flight time", p.flight_time],
                ["Award points", d.award_points]
            ].map((kv) => "<div><dt>" + esc(kv[0]) + "</dt><dd>" +
                          esc(kv[1]) + "</dd></div>").join("");

            el("d-info").innerHTML = rows([
                ["Rank", p.rank],
                ["Squadron", d.squadron],
                ["Status", p.state],
                ["Health", p.health],
                ["Air victories", p.airborne],
                ["Ground targets", p.ground_targets],
                ["Squadron efficiency", d.efficiency]
            ]);
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
                icon("squadron", d.squadron_key, 56, "squadron-emblem strip", d.squadron) +
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

    /* --------------------------------------------------------- navigation -- */

    function route() {
        const match = location.hash.match(/^#career\/(.+)$/);
        const onDetail = Boolean(match);
        show(el("landing-page"), !onDetail);
        show(el("detail-page"), onDetail);
        show(el("back-btn"), onDetail);
        window.scrollTo(0, 0);
        if (onDetail) loadDetail(decodeURIComponent(match[1]));
        else loadLanding();
    }

    el("back-btn").addEventListener("click", () => { location.hash = ""; });
    el("d-roster").querySelectorAll("th").forEach((th) => {
        th.addEventListener("click", () => {
            const key = th.dataset.sort;
            if (!key) return;
            if (key === sortKey) sortAsc = !sortAsc;
            else { sortKey = key; sortAsc = (key === "name" || key === "top_award"); }
            renderRoster();
        });
    });

    window.addEventListener("hashchange", route);
    route();
})();
