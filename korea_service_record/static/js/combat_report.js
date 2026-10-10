(async function () {
    "use strict";

    const el = (id) => document.getElementById(id);
    const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
        ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
    const params = new URLSearchParams(location.search);
    const careerId = params.get("career");
    const wantedMission = Number(params.get("mission"));
    const done = () => { document.body.dataset.ready = "1"; };
    let map = null;

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

    function weaponRows(g) {
        if (!g || !g.available) {
            return '<p class="cr-na">' + esc(T("combat_report.not_available")) + "</p>";
        }
        const row = (name, loaded, expended, returned, hits, rate) =>
            "<tr><td>" + esc(name) + '</td><td class="num">' + esc(number(loaded)) +
            '</td><td class="num">' + esc(expended == null ? "—" : number(expended)) +
            '</td><td class="num">' + esc(returned == null ? "—" : number(returned)) +
            '</td><td class="num">' + esc(hits == null ? "—" : number(hits)) +
            '</td><td class="num">' + esc(rate == null ? "—" : pct(rate)) + "</td></tr>";
        return '<table class="cr-table cr-weapons"><thead><tr><th>' + esc(T("combat_report.weapon")) +
            '</th><th>' + esc(T("combat_report.loaded")) + '</th><th>' + esc(T("combat_report.expended")) +
            '</th><th>' + esc(T("combat_report.returned")) + '</th><th>' +
            esc(T("combat_report.recorded_hits")) + '</th><th>' + esc(T("combat_report.rate")) +
            "</th></tr></thead><tbody>" +
            row(T("combat_report.gun_rounds"), g.gun_loaded, g.gun_fired, g.gun_returned,
                g.gun_hits, g.gun_rate) +
            row(T("combat_report.bombs"), g.bombs_loaded, g.bombs_expended, g.bombs_returned, null, null) +
            row(T("combat_report.rockets"), g.rockets_loaded, g.rockets_expended, g.rockets_returned,
                g.rocket_impacts, g.rockets_expended ? Math.round(1000 * g.rocket_impacts / g.rockets_expended) / 10 : null) +
            "</tbody></table>" + (!g.complete
                ? '<p class="cr-footnote">' + esc(T("combat_report.incomplete")) + "</p>" : "");
    }

    function summaryPage() {
        const s = data.summary;
        const identity = '<div class="cr-fields">' +
            field("pilot", data.pilot.rank + " " + data.pilot.name) +
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
            '</td></tr><tr><th>' + esc(T("combat_report.direct_impacts")) +
            '</th><td class="num" colspan="3">' + number(s.rocket_impacts) + "</td></tr></tbody></table>";
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
        const listedReports = data.reports.slice(0, 20);
        const missionButtons = listedReports.map((r, idx) => {
            const g = r.gunnery || {};
            const figure = g.complete ? number(g.gun_fired) + " / " + number(g.gun_hits) + " / " + pct(g.gun_rate) : "—";
            return '<button class="cr-mission-link" data-report-index="' + (idx + 1) + '"><strong>' +
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
        const flight = [report.takeoff, report.landing_time].filter(Boolean).join(" – ");
        return '<div class="cr-fields">' + field("pilot", data.pilot.rank + " " + data.pilot.name) +
            field("unit", data.squadron) + field("date", report.date + " " + report.time) +
            field("mission_type", report.type) + field("aircraft", report.aircraft || "—") +
            field("airframe", report.airframe || "—") + field("flight", flight || report.duration) +
            field("outcome", T("debrief.outcome_" + report.outcome)) + "</div>";
    }

    function reportLog(report) {
        const rows = [];
        (report.gunnery.passes || []).forEach((p) => rows.push({
            time: p.time, order: 0, html: esc(T("combat_report.attack_pass", {hits: p.hits})) +
                (p.targets.length ? " — " + esc(p.targets.join(", ")) : "")
        }));
        (report.log || []).forEach((item) => {
            if (item.hurt) {
                rows.push({time: item.time, order: 2, html: '<span class="cr-hurt">' +
                    esc(T("combat_report.hit_taken", {hits: item.hurt.hits, damage: item.hurt.total})) + "</span>"});
            } else {
                rows.push({time: item.time, order: 1, html: '<span class="cr-kill">' + esc(item.target) +
                    (item.victim ? " — " + esc(item.victim) : "") + "</span>"});
            }
        });
        rows.sort((a, b) => String(a.time).localeCompare(String(b.time)) || a.order - b.order);
        return rows.length ? '<ol class="cr-log cr-scroll-log">' + rows.slice(0, 16).map((r) =>
            "<li><time>" + esc(r.time || "—") + "</time><span>" + r.html + "</span></li>").join("") + "</ol>"
            : '<p class="cr-na">' + esc(T("combat_report.none")) + "</p>";
    }

    async function renderMap(report) {
        const box = el("cr-map");
        if (!box || !window.KoreaMap || !window.L) return;
        try {
            const mission = await fetch("/api/mission/" + encodeURIComponent(careerId) + "/" + report.mission_id)
                .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); });
            if (!mission.route || !mission.route.length) {
                box.textContent = T("combat_report.map_unavailable");
                return;
            }
            map = KoreaMap.createMap(box, {scrollWheelZoom: false, dragging: false,
                doubleClickZoom: false, boxZoom: false, keyboard: false, touchZoom: false, zoomControl: false});
            const route = KoreaMap.routeLayer({points: mission.route.map((p) => [p.x, p.z, p.type])}, false, T).addTo(map);
            const target = KoreaMap.targetMarker(mission.target, false);
            if (target) target.addTo(map);
            const kills = L.layerGroup((mission.log || []).filter((k) => k.x || k.z).map((k) => k.air
                ? KoreaMap.victoryMarker({x: k.x, z: k.z, alt: k.altitude, target: k.target,
                    victim: k.victim, pilot: k.actor, number: mission.number, date: mission.date,
                    mission_id: mission.id}, T)
                : KoreaMap.groundMarker(k, T))).addTo(map);
            map.invalidateSize();
            KoreaMap.fitTo(map, [route, kills], 0.12);
            fetch("/api/track/" + encodeURIComponent(careerId) + "/" + report.mission_id)
                .then((r) => r.ok ? r.json() : null).then((track) => {
                    if (!track || !map) return;
                    const layers = [];
                    if (track.front && track.front.length > 1) KoreaMap.frontLayer(track.front, T).addTo(map);
                    if (track.segments && track.segments.length) layers.push(KoreaMap.trackLayer(track, T).addTo(map));
                    if (track.losses && track.losses.length) layers.push(KoreaMap.lossLayer(track.losses, T).addTo(map));
                    if (layers.length) KoreaMap.fitTo(map, [route, kills].concat(layers), 0.12);
                }).catch(() => {});
        } catch (_error) {
            box.textContent = T("combat_report.map_unavailable");
        }
    }

    function missionPage(report) {
        const g = report.gunnery || {available: false, passes: [], targets: []};
        const hitsTaken = (report.log || []).filter((x) => x.hurt);
        const hitCount = hitsTaken.reduce((n, x) => n + Number(x.hurt.hits || 0), 0);
        const damage = hitsTaken.reduce((n, x) => Math.max(n, Number(x.hurt.total || 0)), 0);
        el("cr-left").innerHTML = formHead(T("combat_report.mission_report")) + reportFields(report) +
            section(T("combat_report.combat_results"), '<div class="cr-stat-grid">' +
                stat(number(report.airborne), T("combat_report.air_victories")) +
                stat(number(report.ground_targets), T("combat_report.ground_targets")) +
                stat(number(report.assists), T("combat_report.assists")) +
                stat(number(hitCount), T("combat_report.hits_taken")) + "</div>") +
            section(T("combat_report.mission_map"), '<div id="cr-map" class="cr-map"></div>', "cr-map-wrap") +
            '<p class="cr-result-line">' + esc(T("combat_report.result_line", {
                air: report.airborne, ground: report.ground_targets,
                outcome: T("debrief.outcome_" + report.outcome)})) + "</p>" +
            '<div class="cr-signature">' + esc(data.pilot.name) + "</div>";
        const targets = (g.targets || []).length
            ? '<ul class="cr-targets">' + g.targets.map((t) => "<li>" + esc(t.name) + " ×" + number(t.hits) + "</li>").join("") + "</ul>"
            : '<p class="cr-na">' + esc(T("combat_report.none")) + "</p>";
        const damageText = hitCount
            ? T("combat_report.damage_line", {hits: hitCount, damage: damage,
                outcome: T("debrief.outcome_" + report.outcome)})
            : T("combat_report.no_damage", {outcome: T("debrief.outcome_" + report.outcome)});
        const remarks = g.complete
            ? T("combat_report.remarks_line", {fired: g.gun_fired, hits: g.gun_hits,
                rate: g.gun_rate == null ? "—" : number(g.gun_rate),
                air: report.airborne, ground: report.ground_targets})
            : T("combat_report.not_available");
        el("cr-right").innerHTML = formHead(T("combat_report.gunnery_analysis")) +
            section(T("combat_report.weapons_expenditure"), weaponRows(g)) +
            section(T("combat_report.engagement_log"), reportLog(report)) +
            section(T("combat_report.targets_struck"), targets) +
            section(T("combat_report.damage_sustained"), '<p class="cr-remark">' + esc(damageText) + "</p>") +
            section(T("combat_report.remarks"), '<p class="cr-remark">' + esc(remarks) +
                '</p><p class="cr-footnote">' + esc(T("combat_report.method")) + "</p>");
        renderMap(report);
    }

    const views = [{summary: true}].concat(data.reports);
    let current = wantedMission
        ? Math.max(0, views.findIndex((v) => Number(v.mission_id) === wantedMission))
        : 0;
    function render() {
        if (map) { map.remove(); map = null; }
        if (views[current].summary) summaryPage();
        else missionPage(views[current]);
        el("cr-prev").disabled = current <= 0;
        el("cr-next").disabled = current >= views.length - 1;
        el("cr-page").textContent = current === 0
            ? T("combat_report.summary")
            : missionName(views[current].mission_num) + " · " + views[current].date;
        history.replaceState(null, "", "/combat-report?career=" + encodeURIComponent(careerId) +
            (current ? "&mission=" + encodeURIComponent(views[current].mission_id) : ""));
    }
    el("cr-prev").addEventListener("click", () => { if (current > 0) { current -= 1; render(); } });
    el("cr-next").addEventListener("click", () => { if (current + 1 < views.length) { current += 1; render(); } });
    el("cr-note").textContent = data.pilot.rank + " " + data.pilot.name + " · " + data.squadron;
    el("cr-folder").hidden = false;
    el("cr-state").hidden = true;
    render();
    done();
})();
