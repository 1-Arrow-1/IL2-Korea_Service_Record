/**
 * IL-2 Korea Service Record — front end.
 *
 * Two views held in one document: a career list, and the detail for whichever
 * career was clicked. Navigation is by hash so the browser Back button and a
 * page reload both land where the user expects.
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

    async function getJSON(url) {
        const response = await fetch(url);
        if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
        return response.json();
    }

    /* ------------------------------------------------------------ landing -- */

    function careerCard(career) {
        const stat = (value, label) =>
            `<div class="career-stat"><span class="value">${esc(value)}</span>` +
            `<span class="label">${esc(label)}</span></div>`;
        return `
            <button class="career-card" data-id="${esc(career.id)}">
                <div class="career-card-head">
                    <span class="career-pilot">${esc(career.pilot)}</span>
                    <span class="career-rank">${esc(career.rank)}</span>
                </div>
                <div class="career-squadron">${esc(career.squadron)}</div>
                <div class="career-dates">
                    ${esc(career.start_date)} &rarr; ${esc(career.current_date)}
                </div>
                <div class="career-stats">
                    ${stat(career.sorties, "Sorties")}
                    ${stat(career.flight_hours, "Hours")}
                    ${stat(career.airborne, "Air")}
                    ${stat(career.ground_targets, "Ground")}
                    ${stat(career.awards, "Awards")}
                </div>
            </button>`;
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
                card.addEventListener("click",
                    () => { location.hash = "#career/" + encodeURIComponent(card.dataset.id); });
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

    // The roster carries attributes as display rows; flatten so the table can
    // sort on them like any other column.
    function flatten(pilot) {
        const out = Object.assign({}, pilot);
        (pilot.attributes || []).forEach((a) => { out[a.name] = a.level; });
        return out;
    }

    function attributeBlock(attributes) {
        return (attributes || []).map((attr) => {
            const pips = Array.from({ length: 5 }, (_, i) =>
                `<span class="attr-pip${i < attr.level ? " on" : ""}"></span>`).join("");
            const points = attr.points
                ? `<span class="attr-points">&uarr;${esc(attr.points)}</span>` : "";
            return `
                <div class="attr-row">
                    <div class="attr-head">
                        <span>${esc(attr.name)}</span>
                        <span><span class="attr-value">${esc(attr.level)}</span>${points}</span>
                    </div>
                    <div class="attr-bar">${pips}</div>
                </div>`;
        }).join("");
    }

    function awardItem(award) {
        const badges =
            (award.pending ? '<span class="badge pending">pending</span>' : "") +
            (award.is_promotion ? '<span class="badge promotion">promotion</span>' : "");
        const received = award.pending
            ? "awaiting award points"
            : `received ${esc(award.received)}`;
        return `<li>
            <span class="award-name">${esc(award.name)}${badges}</span>
            <span class="award-dates">earned ${esc(award.earned)} &middot; ${received}</span>
        </li>`;
    }

    function serviceItem(entry) {
        let text = esc(entry.label);
        if (entry.award) {
            const verb = entry.action === "granted" ? "Awarded" : "Presented";
            text = `${verb}: ${esc(entry.award)}`;
            if (entry.action === "granted") {
                const route = entry.route === "mission"
                    ? "earned in the air" : "roster review";
                text += `<span class="service-route">${route}</span>`;
            }
        } else if (entry.aircraft) {
            text = `${esc(entry.label)} &mdash; ${esc(entry.aircraft)}`;
        } else if (entry.health !== undefined) {
            text = entry.phase === "returned"
                ? esc(entry.label) + " &mdash; returned to duty"
                : `${esc(entry.label)} &mdash; health ${esc(entry.health)}`;
        }
        return `<li class="kind-${esc(entry.kind)}">
            <span class="service-date">${esc(entry.date)}</span>
            <span class="service-text">${text}</span>
        </li>`;
    }

    function renderRoster() {
        const body = el("d-roster").querySelector("tbody");
        const rows = rosterRows.slice().sort((a, b) => {
            const x = a[sortKey], y = b[sortKey];
            const cmp = (typeof x === "string")
                ? String(x).localeCompare(String(y))
                : (Number(x) || 0) - (Number(y) || 0);
            return sortAsc ? cmp : -cmp;
        });
        body.innerHTML = rows.map((p) => {
            const dotClass = ["active", "kia", "wounded", "pow"].includes(p.state)
                ? "status-" + p.state : "status-other";
            const cls = [p.is_player ? "is-player" : "", p.state === "kia" ? "is-kia" : ""]
                .filter(Boolean).join(" ");
            return `<tr class="${cls}">
                <td>${esc(p.name)}</td>
                <td>${esc(p.rank)}</td>
                <td><span class="status-dot ${dotClass}"></span>${esc(p.state)}</td>
                <td class="num">${esc(p.sorties)}</td>
                <td class="num">${esc(p.flight_hours)}</td>
                <td class="num">${esc(p.airborne)}</td>
                <td class="num">${esc(p.ground_targets)}</td>
                <td class="num">${esc(p.skills)}</td>
                <td class="num">${esc(p.discipline)}</td>
                <td class="num">${esc(p.courage)}</td>
                <td class="num">${esc(p.awards_held)}</td>
                <td class="num">${p.awards_pending ? esc(p.awards_pending) : ""}</td>
            </tr>`;
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
            el("d-subtitle").textContent = `${p.rank} · ${d.squadron}`;
            el("d-meta").innerHTML = [
                ["Career", `${d.start_date} – ${d.current_date}`],
                ["Sorties", `${p.sorties} (${p.good_sorties} successful)`],
                ["Flight hours", p.flight_hours],
                ["Award points", d.award_points],
            ].map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join("");

            el("d-attributes").innerHTML = attributeBlock(p.attributes);
            el("d-efficiency").innerHTML = `
                <tr><th>Air victories</th><td>${esc(p.airborne)}</td></tr>
                <tr><th>Ground targets</th><td>${esc(p.ground_targets)}</td></tr>
                <tr><th>Squadron efficiency</th><td>${esc(d.efficiency)}</td></tr>`;

            el("d-awards").innerHTML = d.player_awards.length
                ? d.player_awards.map(awardItem).join("")
                : "<li>No awards yet.</li>";

            el("d-service").innerHTML = d.service_record.length
                ? d.service_record.map(serviceItem).join("")
                : "<li>Nothing recorded yet.</li>";

            rosterRows = d.roster.map(flatten);
            el("d-roster-count").textContent = `(${rosterRows.length})`;
            renderRoster();
            el("d-pending-note").textContent = d.pending_total
                ? `${d.pending_total} awards are waiting on award points; you have ${d.award_points}.`
                : "";

            show(el("detail-loading"), false);
            show(el("detail-body"));
        } catch (err) {
            el("detail-loading").innerHTML =
                `<p class="state-message">Could not open that career: ${esc(err.message)}</p>`;
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
            else { sortKey = key; sortAsc = key === "name"; }
            renderRoster();
        });
    });

    window.addEventListener("hashchange", route);
    route();
})();
