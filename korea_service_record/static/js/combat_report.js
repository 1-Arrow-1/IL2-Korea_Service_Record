(async function () {
    "use strict";

    const el = (id) => document.getElementById(id);
    const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
        ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
    const params = new URLSearchParams(location.search);
    const careerId = params.get("career");
    const wantedMission = Number(params.get("mission"));
    const wantedSection = params.get("section") || "details";
    const done = () => { document.body.dataset.ready = "1"; };

    const settings = await fetch("/api/settings").then((r) => r.json()).catch(() => ({}));
    const override = (settings.overrides || []).find((o) => o.career === careerId);
    const pageLang = (override && override.language) || settings.language || "en";
    await i18n.init(pageLang);
    i18n.apply(document.body);
    const T = (key, values) => i18n.t(key, values);
    document.title = T("combat_report.title");

    const back = el("cr-back");
    back.href = careerId ? "/#career/" + encodeURIComponent(careerId) : "/";
    back.addEventListener("click", (event) => {
        const parent = window.opener;
        if (!parent || parent.closed) return;
        event.preventDefault();
        try {
            parent.location.href = back.href;
            parent.focus();
            window.close();
            setTimeout(() => { if (!window.closed) window.location.href = back.href; }, 100);
        } catch (_error) { window.location.href = back.href; }
    });
    el("cr-print").addEventListener("click", () => window.print());

    if (!careerId) {
        el("cr-state").textContent = T("combat_report.failed");
        done();
        return;
    }

    let data;
    try {
        const response = await fetch("/api/combat-report/" + encodeURIComponent(careerId));
        if (!response.ok) throw new Error(response.status);
        data = await response.json();
    } catch (_error) {
        el("cr-state").textContent = T("combat_report.failed");
        done();
        return;
    }

    const number = (value) => Number(value || 0).toLocaleString(pageLang);
    const pct = (value) => value == null ? "—" : number(value) + "%";
    const bombFigure = (g) => g.bomb_hits == null || g.bomb_targets == null
        ? "—" : number(g.bomb_hits) + " (" + number(g.bomb_targets) + ")";
    const missionName = (n) => Number(n) < 0
        ? T("debrief.unscheduled", {number: -Number(n)})
        : T("combat_report.mission", {number: n});
    const service = () => T("combat_report.service_" + data.pilot.country);
    const seal = () => data.seal
        ? '<img class="cr-seal" alt="" src="/static/images/stamps/seal_' + esc(data.seal) + '.png">'
        : "";
    const field = (key, value) => '<div class="cr-field"><span class="cr-k">' +
        esc(T("combat_report." + key)) + '</span><span class="cr-v" title="' +
        esc(value) + '">' + esc(value || "—") + "</span></div>";
    const stat = (value, label) => '<div class="cr-stat"><strong>' + esc(value) +
        "</strong><span>" + esc(label) + "</span></div>";
    const section = (title, body, cls) => '<section class="cr-section ' + (cls || "") +
        '"><h2>' + esc(title) + "</h2>" + body + "</section>";
    const formHead = (title) => '<header class="cr-form-head">' + seal() +
        '<p class="cr-service">' + esc(service()) + "</p><h1>" + esc(title) +
        '</h1><span class="cr-classification">' + esc(T("combat_report.restricted")) + "</span></header>";

    const pilotCandidates = () => {
        const first = String(data.pilot.first_name || "").trim();
        const last = String(data.pilot.last_name || "").trim();
        const fullName = String(data.pilot.name || [first, last].filter(Boolean).join(" ")).trim();
        const short = typeof window.shortRank === "function" ? window.shortRank(data.pilot.rank) : data.pilot.rank;
        const initialName = first && last ? first.charAt(0) + ". " + last : fullName;
        return Array.from(new Set([
            [data.pilot.rank, fullName].filter(Boolean).join(" "),
            [short, fullName].filter(Boolean).join(" "),
            [short, initialName].filter(Boolean).join(" ")
        ].map((value) => value.trim()).filter(Boolean)));
    };
    const pilotField = () => {
        const full = pilotCandidates()[0] || "—";
        return '<div class="cr-field"><span class="cr-k">' + esc(T("combat_report.pilot")) +
            '</span><span class="cr-v cr-pilot-name" title="' + esc(full) + '">' + esc(full) + "</span></div>";
    };
    const fitPilotNames = (root) => {
        const candidates = pilotCandidates();
        root.querySelectorAll(".cr-pilot-name").forEach((line) => {
            line.style.fontSize = "";
            for (const candidate of candidates) {
                line.textContent = candidate;
                if (line.clientWidth && line.scrollWidth <= line.clientWidth) return;
            }
            const room = line.clientWidth;
            const width = line.scrollWidth;
            if (room && width > room) line.style.fontSize = Math.min(1, room / width * 0.97) + "em";
        });
    };
    function weaponRows(g) {
        if (!g || !g.available) {
            return '<p class="cr-na">' + esc(T("combat_report.not_available")) + "</p>";
        }
        const shownHits = (hits) => hits == null ? "—" :
            (typeof hits === "string" ? hits : number(hits));
        const row = (name, loaded, expended, returned, hits, rate) =>
            "<tr><td>" + esc(name) + '</td><td class="num">' + esc(number(loaded)) +
            '</td><td class="num">' + esc(expended == null ? "—" : number(expended)) +
            '</td><td class="num">' + esc(returned == null ? "—" : number(returned)) +
            '</td><td class="num">' + esc(shownHits(hits)) +
            '</td><td class="num">' + esc(rate == null ? "—" : pct(rate)) + "</td></tr>";
        return '<table class="cr-table cr-weapons"><thead><tr><th>' + esc(T("combat_report.weapon")) +
            '</th><th>' + esc(T("combat_report.loaded")) + '</th><th>' + esc(T("combat_report.expended")) +
            '</th><th>' + esc(T("combat_report.returned")) + '</th><th>' +
            esc(T("combat_report.recorded_hits")) + '</th><th>' + esc(T("combat_report.rate")) +
            "</th></tr></thead><tbody>" +
            row(T("combat_report.gun_rounds"), g.gun_loaded, g.gun_fired, g.gun_returned,
                g.gun_hits, g.gun_rate) +
            row(T("combat_report.bombs"), g.bombs_loaded, g.bombs_expended, g.bombs_returned,
                bombFigure(g), g.bomb_rate) +
            row(T("combat_report.rockets"), g.rockets_loaded, g.rockets_expended, g.rockets_returned,
                g.rocket_impacts, g.rockets_expended ? Math.round(1000 * g.rocket_impacts / g.rockets_expended) / 10 : null) +
            "</tbody></table>" + (!g.complete
                ? '<p class="cr-footnote">' + esc(T("combat_report.incomplete")) + "</p>" : "");
    }

    function summaryPage() {
        const s = data.summary;
        const identity = '<div class="cr-fields">' +
            pilotField() +
            field("unit", data.squadron) + field("date", data.as_of) +
            field("missions_covered_short", s.covered + " / " + s.missions) + "</div>";
        const totals = '<div class="cr-summary-big">' +
            '<div class="cr-summary-card"><strong>' + number(s.gun_fired) + "</strong><span>" +
                esc(T("combat_report.rounds_fired")) + "</span></div>" +
            '<div class="cr-summary-card"><strong>' + number(s.gun_hits) + "</strong><span>" +
                esc(T("combat_report.recorded_hits")) + "</span></div>" +
            '<div class="cr-summary-card"><strong>' + pct(s.gun_rate) + "</strong><span>" +
                esc(T("combat_report.overall_rate")) + "</span></div>" +
            '<div class="cr-summary-card"><strong>' + number(s.airborne + s.ground_targets) + "</strong><span>" +
                esc(T("combat_report.targets_destroyed")) + "</span></div></div>";
        const stores = '<table class="cr-table"><tbody><tr><th>' + esc(T("combat_report.bombs")) +
            '</th><td class="num">' + number(s.bombs_expended) + '</td><th>' +
            esc(T("combat_report.rockets")) + '</th><td class="num">' + number(s.rockets_expended) +
            '</td></tr><tr><th>' + esc(T("combat_report.bomb_hits")) +
            '</th><td class="num">' + esc(number(s.bomb_hits) + " (" + number(s.bomb_targets) + ")") +
            '</td><th>' + esc(T("combat_report.direct_impacts")) +
            '</th><td class="num">' + number(s.rocket_impacts) + "</td></tr></tbody></table>";
        const aircraft = s.by_aircraft.length
            ? '<table class="cr-table"><thead><tr><th>' + esc(T("combat_report.aircraft")) +
                '</th><th>' + esc(T("combat_report.missions_covered_short")) + '</th><th>' +
                esc(T("combat_report.rounds_fired")) + '</th><th>' +
                esc(T("combat_report.recorded_hits")) + '</th><th>' +
                esc(T("combat_report.rate")) + '</th></tr></thead><tbody>' +
                s.by_aircraft.map((a) => '<tr><td>' + esc(a.aircraft) + '</td><td class="num">' +
                    number(a.missions) + '</td><td class="num">' + number(a.gun_fired) +
                    '</td><td class="num">' + number(a.gun_hits) + '</td><td class="num">' +
                    pct(a.gun_rate) + "</td></tr>").join("") + "</tbody></table>"
            : '<p class="cr-na">' + esc(T("combat_report.no_data")) + "</p>";
        el("cr-left").innerHTML = '<div class="cr-summary-title">' + seal() + '<p class="cr-service">' +
            esc(service()) + "</p><h1>" + esc(T("combat_report.career_summary")) + "</h1><p>" +
            esc(data.pilot.rank + " " + data.pilot.name) + "</p></div>" + identity + totals +
            section(T("combat_report.ordnance_expended"), stores) +
            '<p class="cr-footnote">' + esc(T("combat_report.coverage", {covered: s.complete, total: s.missions})) +
            "</p><p class=\"cr-footnote\">" + esc(T("combat_report.method")) + "</p>";
        fitPilotNames(el("cr-left"));
        const listedReports = data.reports.slice(0, 20);
        const missionButtons = listedReports.map((r, idx) => {
            const g = r.gunnery || {};
            const figure = g.complete ? number(g.gun_fired) + " / " + number(g.gun_hits) + " / " + pct(g.gun_rate) : "—";
            return '<button class="cr-mission-link" data-report-index="' + (idx * 2 + 1) + '"><strong>' +
                esc(missionName(r.mission_num)) + "</strong> " + esc(r.date) + "<span>" + esc(figure) + "</span></button>";
        }).join("");
        el("cr-right").innerHTML = formHead(T("combat_report.gunnery_analysis")) +
            section(T("combat_report.by_aircraft"), aircraft) +
            section(T("combat_report.mission_reports"), '<div class="cr-mission-list">' + missionButtons + "</div>" +
                (data.reports.length > listedReports.length ? '<p class="cr-footnote cr-earlier">' +
                    esc(T("combat_report.earlier_reports", {count: data.reports.length - listedReports.length})) +
                    "</p>" : ""));
        el("cr-right").querySelectorAll("[data-report-index]").forEach((button) => {
            button.addEventListener("click", () => { current = Number(button.dataset.reportIndex); render(); });
        });
    }

    function reportFields(report) {
        return '<div class="cr-fields">' + pilotField() +
            field("unit", data.squadron) + field("date", report.date + " " + report.time) +
            field("mission_type", report.type) + field("aircraft", report.aircraft || "—") +
            field("airframe", report.airframe || "—") + field("flight", report.duration) +
            field("outcome", T("debrief.outcome_" + report.outcome)) + "</div>";
    }

    function reportLog(gunnery) {
        const rows = (gunnery.passes || []).map((pass) => ({
            time: pass.time,
            html: esc(T("combat_report.attack_pass", {hits: pass.hits})) +
                (pass.targets.length ? " — " + esc(pass.targets.join(", ")) : "")
        })).concat((gunnery.bomb_attacks || []).map((attack) => ({
            time: attack.time,
            html: esc(T("combat_report.bomb_attack", {targets: attack.targets}))
        }))).sort((a, b) => String(a.time).localeCompare(String(b.time)));
        return rows.length ? '<ol class="cr-log cr-attack-log">' + rows.slice(0, 16).map((row) =>
            "<li><time>" + esc(row.time || "—") + "</time><span>" + row.html + "</span></li>").join("") + "</ol>"
            : '<p class="cr-na">' + esc(T("combat_report.none")) + "</p>";
    }

    function combatPage(report) {
        const g = report.gunnery || {available: false, passes: [], targets: []};
        const overview = g.available
            ? '<div class="cr-stat-grid">' +
                stat(number(g.gun_fired), T("combat_report.rounds_fired")) +
                stat(number(g.gun_hits), T("combat_report.recorded_hits")) +
                stat(pct(g.gun_rate), T("combat_report.overall_rate")) +
                (g.bombs_expended
                    ? stat(bombFigure(g), T("combat_report.bomb_hits"))
                    : stat(number(g.rocket_impacts), T("combat_report.direct_impacts"))) + "</div>"
            : '<p class="cr-na">' + esc(T("combat_report.not_available")) + "</p>";
        el("cr-left").innerHTML = formHead(T("combat_report.gunnery_analysis")) +
            '<p class="cr-context">' + esc(missionName(report.mission_num)) + " · " +
                esc(report.date) + " · " + esc(report.aircraft || "—") + "</p>" +
            section(T("combat_report.gunnery_analysis"), overview) +
            section(T("combat_report.engagement_log"), reportLog(g)) +
            '<div class="cr-signature">' + esc(data.pilot.name) + "</div>";
        fitPilotNames(el("cr-left"));
        const targets = (g.targets || []).length
            ? '<ul class="cr-targets">' + g.targets.map((target) => "<li>" + esc(target.name) + " ×" + number(target.hits) + "</li>").join("") + "</ul>"
            : '<p class="cr-na">' + esc(T("combat_report.none")) + "</p>";
        const remarks = g.complete
            ? T("combat_report.remarks_line", {fired: g.gun_fired, hits: g.gun_hits,
                rate: g.gun_rate == null ? "—" : number(g.gun_rate)})
            : T("combat_report.not_available");
        el("cr-right").innerHTML = formHead(T("combat_report.gunnery_analysis")) +
            section(T("combat_report.weapons_expenditure"), weaponRows(g)) +
            section(T("combat_report.targets_struck"), targets) +
            section(T("combat_report.remarks"), '<p class="cr-remark">' + esc(remarks) +
                '</p><p class="cr-footnote">' + esc(T("combat_report.method")) + "</p>");
    }

    function briefingParagraphs(raw) {
        const text = String(raw || "")
            .replace(/<\s*br\s*\/?>/gi, "\n")
            .replace(/<\/(h1|h2|p|div)>/gi, "\n\n")
            .replace(/<[^>]*>/g, "")
            .replace(/&nbsp;/gi, " ");
        return text.split(/\n\s*\n/).map((part) => part.trim()).filter(Boolean);
    }

    function detailTimeline(mission) {
        const player = (mission.flown || []).find((pilot) => pilot.is_player) || {};
        const rows = (mission.log || []).filter((row) => row.by_player).map((row) => ({
            time: row.time,
            order: 0,
            html: '<span class="cr-kill">' + esc(row.target || row.victim || "—") +
                (row.victim && row.victim !== row.target ? " — " + esc(row.victim) : "") + "</span>"
        })).concat((player.damage_log || []).map((row) => ({
            time: row.time,
            order: 1,
            html: '<span class="cr-hurt">' + esc(T("combat_report.hit_taken", {
                hits: row.hits, damage: row.total})) +
                (row.attacker ? " — " + esc(row.attacker) : "") + "</span>"
        })));
        rows.sort((a, b) => String(a.time).localeCompare(String(b.time)) || a.order - b.order);
        return rows.length ? '<ol class="cr-log cr-detail-log">' + rows.map((row) =>
            "<li><time>" + esc(row.time || "—") + "</time><span>" + row.html + "</span></li>").join("") + "</ol>"
            : '<p class="cr-na">' + esc(T("combat_report.none")) + "</p>";
    }

    function flightRoster(mission) {
        const pilots = mission.flown || [];
        if (!pilots.length) return '<p class="cr-na">' + esc(T("combat_report.none")) + "</p>";
        return '<table class="cr-table cr-flight-table"><thead><tr><th>' +
            esc(T("debrief.rank")) + "</th><th>" + esc(T("debrief.name")) +
            '</th><th class="num">' + esc(T("debrief.air")) + '</th><th class="num">' +
            esc(T("debrief.ground")) + '</th><th class="num">' + esc(T("debrief.time")) +
            "</th><th>" + esc(T("debrief.outcome")) + "</th></tr></thead><tbody>" +
            pilots.map((pilot) => '<tr' + (pilot.is_player ? ' class="is-player"' : "") + "><td>" +
                esc(typeof window.shortRank === "function" ? window.shortRank(pilot.rank) : pilot.rank) +
                "</td><td>" + esc(pilot.name) + '</td><td class="num">' + number(pilot.airborne) +
                '</td><td class="num">' + number(pilot.ground_targets) + '</td><td class="num">' +
                esc(pilot.flight_time) + "</td><td>" + esc(T("debrief.outcome_" + pilot.outcome)) +
                (pilot.wounded ? " · " + esc(T("debrief.wounded")) : "") + "</td></tr>").join("") +
            "</tbody></table>";
    }

    let map = null;
    let renderToken = 0;
    const detailCache = new Map();
    async function renderMap(mission, token) {
        const box = el("cr-map");
        if (!box || token !== renderToken || !window.KoreaMap || !window.L) return;
        if (!mission.route || !mission.route.length) {
            box.textContent = T("combat_report.map_unavailable");
            return;
        }
        map = KoreaMap.createMap(box, {scrollWheelZoom: true, dragging: true,
            doubleClickZoom: false, boxZoom: false, keyboard: false,
            touchZoom: false, zoomControl: false});
        const route = KoreaMap.routeLayer({points: mission.route.map((point) =>
            [point.x, point.z, point.type])}, false, T).addTo(map);
        const target = KoreaMap.targetMarker(mission.target, false);
        if (target) target.addTo(map);
        const kills = L.layerGroup((mission.log || []).filter((row) => row.x || row.z).map((row) =>
            row.air ? KoreaMap.victoryMarker({x: row.x, z: row.z, alt: row.altitude,
                target: row.target, victim: row.victim, pilot: row.actor,
                number: mission.number, date: mission.date, mission_id: mission.id}, T)
                : KoreaMap.groundMarker(row, T))).addTo(map);
        map.invalidateSize();
        KoreaMap.fitTo(map, [route, kills], 0.12);
        try {
            const response = await fetch("/api/track/" + encodeURIComponent(careerId) + "/" + mission.id);
            const track = response.ok ? await response.json() : null;
            if (!track || !map || token !== renderToken) return;
            const layers = [];
            if (track.front && track.front.length > 1) KoreaMap.frontLayer(track.front, T).addTo(map);
            if (track.segments && track.segments.length) layers.push(KoreaMap.trackLayer(track, T).addTo(map));
            if (track.losses && track.losses.length) layers.push(KoreaMap.lossLayer(track.losses, T).addTo(map));
            if (layers.length) KoreaMap.fitTo(map, [route, kills].concat(layers), 0.12);
        } catch (_error) { /* The briefed route remains useful without a track. */ }
    }

    async function detailsPage(report, token) {
        el("cr-left").innerHTML = formHead(T("combat_report.mission_report")) + reportFields(report) +
            '<p class="cr-na">' + esc(T("common.loading")) + "</p>";
        el("cr-right").innerHTML = formHead(T("combat_report.details_page"));
        fitPilotNames(el("cr-left"));
        try {
            let mission = detailCache.get(report.mission_id);
            if (!mission) {
                const response = await fetch("/api/mission/" + encodeURIComponent(careerId) + "/" + report.mission_id);
                if (!response.ok) throw new Error(response.status);
                mission = await response.json();
                detailCache.set(report.mission_id, mission);
            }
            if (token !== renderToken) return;
            const player = (mission.flown || []).find((pilot) => pilot.is_player) || {};
            const hitsTaken = (player.damage_log || []).reduce((total, row) => total + Number(row.hits || 0), 0);
            const brief = briefingParagraphs(mission.briefing).map((part) => "<p>" + esc(part) + "</p>").join("") ||
                '<p class="cr-na">' + esc(T("debrief.no_briefing")) + "</p>";
            const results = '<div class="cr-stat-grid">' +
                stat(number(report.airborne), T("combat_report.air_victories")) +
                stat(number(report.ground_targets), T("combat_report.ground_targets")) +
                stat(number(report.assists), T("combat_report.assists")) +
                stat(number(hitsTaken), T("combat_report.hits_taken")) + "</div>";
            el("cr-left").innerHTML = formHead(T("combat_report.mission_report")) + reportFields(report) +
                section(T("combat_report.combat_results"), results) +
                section(T("combat_report.mission_map"), '<div id="cr-map" class="cr-map"></div>', "cr-map-wrap") +
                section(T("combat_report.briefing"), '<div class="cr-briefing">' + brief + "</div>");
            fitPilotNames(el("cr-left"));
            const facts = '<p><strong>' + esc(T("debrief.loadout")) + ":</strong> " +
                esc(report.loadout || T("debrief.guns_only")) + "</p><p>" +
                esc(T("debrief.took_off")) + " " + esc(report.takeoff || "—") + " · " +
                esc(T("debrief.landed")) + " " + esc(report.landing_time || "—") + " · " +
                esc(T("debrief.objectives", {met: mission.obj_success, failed: mission.obj_failure})) +
                (report.fuel_pct == null ? "" : " · " + esc(T("debrief.fuel", {percent: report.fuel_pct}))) +
                (report.range_km == null ? "" : " · " + esc(T("debrief.range", {km: report.range_km}))) + "</p>";
            el("cr-right").innerHTML = formHead(T("combat_report.details_page")) +
                '<div class="cr-detail-facts">' + facts + "</div>" +
                section(T("debrief.pilots_on_mission"), flightRoster(mission), "cr-roster-section") +
                section(T("combat_report.mission_events"), detailTimeline(mission), "cr-events-section");
            renderMap(mission, token);
        } catch (_error) {
            if (token !== renderToken) return;
            el("cr-right").innerHTML += '<p class="cr-na">' + esc(T("combat_report.failed")) + "</p>";
        }
    }

    const views = [{summary: true}];
    data.reports.forEach((report) => {
        views.push({report: report, section: "details"});
        views.push({report: report, section: "combat"});
    });
    let current = wantedMission
        ? Math.max(0, views.findIndex((view) => view.report &&
            Number(view.report.mission_id) === wantedMission && view.section === wantedSection))
        : 0;
    async function render() {
        const token = ++renderToken;
        if (map) { map.remove(); map = null; }
        const view = views[current];
        if (view.summary) summaryPage();
        else if (view.section === "details") await detailsPage(view.report, token);
        else combatPage(view.report);
        el("cr-prev").disabled = current <= 0;
        el("cr-next").disabled = current >= views.length - 1;
        el("cr-page").textContent = current === 0
            ? T("combat_report.summary")
            : missionName(view.report.mission_num) + " · " + view.report.date + " · " +
                T("combat_report." + (view.section === "details" ? "details_page" : "combat_page"));
        history.replaceState(null, "", "/combat-report?career=" + encodeURIComponent(careerId) +
            (current ? "&mission=" + encodeURIComponent(view.report.mission_id) +
                "&section=" + encodeURIComponent(view.section) : ""));
    }
    el("cr-prev").addEventListener("click", () => { if (current > 0) { current -= 1; render(); } });
    el("cr-next").addEventListener("click", () => { if (current + 1 < views.length) { current += 1; render(); } });
    el("cr-note").textContent = data.pilot.rank + " " + data.pilot.name + " · " + data.squadron;
    el("cr-folder").hidden = false;
    el("cr-state").hidden = true;
    render();
    done();
})();
