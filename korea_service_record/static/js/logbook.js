/*
 * The individual flight record, one sheet per month, on the form the
 * pilot's own air force used: the AF Form 5 for the USAF (an English
 * document, whatever the page's language), the flight book for the Soviet
 * Air Force (a Russian one), and the Korean People's Army's book in the
 * page's language, since there is no fixed one here. The page chrome -
 * the bar at the top - follows the page's language.
 *
 * Strings: logbook.* in the locale files. The form's own text comes from
 * the form language's bundle (loaded beside the page's), so a German
 * reader of an American record sees "INDIVIDUAL FLIGHT RECORD" and a
 * German button to print it.
 */
(async function () {
    "use strict";

    // The GRADE box is narrow, so long rank names are shortened there
    // (js/ranks.js); the signature line and the tooltip keep the full name.

    const el = (id) => document.getElementById(id);
    const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
        ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
    const params = new URLSearchParams(location.search);
    const careerId = params.get("career");
    const pilotId = params.get("pilot");
    // Embedded in the personnel file: one month's sheet alone (?month=1951.06),
    // and a mark on the body when it is drawn so the file can measure it.
    const embedded = params.get("embed") === "1";
    const embedMonth = params.get("month");
    if (embedded) document.body.classList.add("embed");
    const done = () => { document.body.dataset.ready = "1"; };

    const settings = await fetch("/api/settings").then((r) => r.json()).catch(() => ({}));
    const override = (settings.overrides || []).find((o) => o.career === careerId);
    const pageLang = (override && override.language) || settings.language || "en";
    await i18n.init(pageLang);
    i18n.apply(document.body);
    const back = el("lb-back");
    back.href = careerId ? "/#career/" + encodeURIComponent(careerId) : "/";
    back.addEventListener("click", (event) => {
        // These pages are opened by the Service Record. Return to that tab
        // and close this one instead of turning it into a duplicate copy.
        const parent = window.opener;
        if (!parent || parent.closed) { return; }
        event.preventDefault();
        const href = back.href;
        try {
            parent.location.href = href;
            parent.focus();
            window.close();
            // A browser can refuse scripted closing under unusual window
            // policies. Keep the ordinary link behavior as the fallback.
            setTimeout(() => {
                if (!window.closed) { window.location.href = href; }
            }, 100);
        } catch (_error) {
            window.location.href = href;
        }
    });
    el("lb-print").addEventListener("click", () => window.print());

    if (!careerId) {
        el("lb-state").textContent = "?"; el("lb-state").hidden = false;
        return;
    }
    let data;
    try {
        const r = await fetch("/api/logbook/" + encodeURIComponent(careerId) + (pilotId ? "/" + encodeURIComponent(pilotId) : ""));
        if (!r.ok) throw new Error(r.status);
        data = await r.json();
    } catch (err) {
        el("lb-state").textContent = i18n.t("logbook.failed"); el("lb-state").hidden = false;
        done();
        return;
    }

    // The form's language: the document's own where it has one.
    // The form keeps its own language whatever the page speaks: English on
    // the Form 5, Russian on the flight book - the Korean People's Army
    // took its paperwork from its Soviet advisers, as its award sheets do.
    const formLang = {usaf: "en", navy: "en", sov: "ru", dprk: "ru"}[data.form] || pageLang;
    if (formLang !== pageLang) await i18n.load(formLang);
    const bundle = i18n.loaded[formLang] || i18n.loaded[pageLang];
    const TF = (key, p) => {
        let text = i18n._lookup(bundle, key);
        if (text === null) text = i18n.t(key, p);
        else if (p) text = text.replace(/\{(\w+)\}/g, (m, n) => (n in p ? String(p[n]) : m));
        return text;
    };
    document.documentElement.lang = formLang;
    document.title = TF("logbook.form.title") + " — " + data.pilot.name;
    el("lb-note").textContent = i18n.t(data.corrected ? "logbook.note_corrected" : "logbook.note");

    const monthName = (key) => {
        const [y, m] = key.split(".");
        const d = new Date(Date.UTC(+y, +m - 1, 1));
        return d.toLocaleDateString(formLang, {month: "long", year: "numeric", timeZone: "UTC"});
    };
    const tenths = (h) => (h == null ? "" : (+h).toFixed(1));
    // Remarks as a real form had them: the mission symbol (USAF only) and
    // the aircraft destroyed, nothing else.
    const remarks = (r) => {
        const out = [];
        if (data.form === "usaf" && r.symbol) out.push(r.symbol);
        const kills = {};
        (r.remarks || []).forEach((k) => { if (typeof k === "string") kills[k] = (kills[k] || 0) + 1; });
        Object.keys(kills).forEach((name) => out.push((kills[name] > 1 ? kills[name] + " × " : "1 ") + name + " " + TF("logbook.form.destroyed")));
        return out.join(" · ");
    };

    if (embedded && embedMonth) {
        data.months = data.months.filter((mo) => mo.month === embedMonth);
    }

    // The Navy's and Marine Corps' Aviator's Flight Log Book: a two-page
    // spread a month, written by hand on the printed ledger
    // (certificates/Vintage_Blank_Flight_Logbook_Ledger.jpg, 1448 x 1086),
    // after Lt. W. E. Bancroft's book of August 1951. 22 ruled lines a
    // spread; a busy month runs onto the next, totals carried forward.
    // Positions are the ledger's own pixels.
    const NAVY_W = 1448, NAVY_H = 1086, NAVY_TOP = 132, NAVY_PITCH = 35.27, NAVY_LINES = 22;
    const NAVY_COLS = {day: [75, 115], model: [115, 219], bureau: [219, 328], char: [328, 386],
        pilot: [386, 445], copilot: [445, 503], student: [503, 562], passenger: [562, 623], total: [623, 700],
        instrument: [752, 816], me_day: [816, 877], me_night: [877, 936], se_night: [936, 995],
        carrier: [995, 1064], remarks: [1068, 1398]};
    const NAVY_TOTALS = [[908, 947], [947, 985], [985, 1024]];
    const navyCell = (cls, col, y0, y1, text) => {
        const [x0, x1] = NAVY_COLS[col];
        return '<span class="nv ' + cls + '" style="left:' + (x0 / NAVY_W * 100) + "%;width:" + ((x1 - x0) / NAVY_W * 100) +
            "%;top:" + (y0 / NAVY_H * 100) + "%;height:" + ((y1 - y0) / NAVY_H * 100) + '%">' + esc(text) + "</span>";
    };
    const navySpreads = () => {
        const out = [];
        let carried = {pilot: 0, total: 0, se_night: 0, carrier: 0};
        data.months.forEach((mo, n) => {
            // Brought forward: the career's hours before this month - right
            // even when one month is shown alone in the personnel file.
            if (n === 0 && mo.to_date && mo.totals) {
                carried = {pilot: mo.to_date.hours - mo.totals.hours, total: mo.to_date.hours - mo.totals.hours,
                           se_night: (mo.to_date.night || 0) - (mo.totals.night || 0), carrier: 0};
            }
            const [y, m] = mo.month.split(".");
            const monthWord = new Date(Date.UTC(+y, +m - 1, 1)).toLocaleDateString("en", {month: "long", timeZone: "UTC"}).toUpperCase();
            for (let start = 0; start === 0 || start < mo.rows.length; start += NAVY_LINES) {
                const rows = mo.rows.slice(start, start + NAVY_LINES);
                const page = {pilot: 0, total: 0, se_night: 0, carrier: 0};
                let html = '<span class="nv head" style="left:9.6%;top:1.6%;width:14%">' + esc(monthWord) + "</span>" +
                    '<span class="nv head" style="left:34.5%;top:1.6%;width:10%">' + esc(y) + "</span>";
                rows.forEach((r, i) => {
                    const y0 = NAVY_TOP + i * NAVY_PITCH, y1 = y0 + NAVY_PITCH;
                    const night = r.night_h || 0;
                    page.pilot += r.hours; page.total += r.hours; page.se_night += night; page.carrier += 0;
                    html += navyCell("c", "day", y0, y1, r.day) + navyCell("", "model", y0, y1, r.aircraft) +
                        navyCell("c", "bureau", y0, y1, r.bureau || "") + navyCell("c", "char", y0, y1, r.char || "") +
                        navyCell("c", "pilot", y0, y1, tenths(r.hours)) + navyCell("c", "total", y0, y1, tenths(r.hours)) +
                        (night ? navyCell("c", "se_night", y0, y1, tenths(night)) : "") +
                        navyCell("rm", "remarks", y0, y1, [r.mission, remarks(r)].filter(Boolean).join(" · "));
                });
                const grand = {};
                Object.keys(page).forEach((k) => { grand[k] = carried[k] + page[k]; });
                [[page, 0], [carried, 1], [grand, 2]].forEach(([t, n]) => {
                    const [y0, y1] = NAVY_TOTALS[n];
                    html += navyCell("c tot", "pilot", y0, y1, tenths(t.pilot)) + navyCell("c tot", "total", y0, y1, tenths(t.total)) +
                        (t.se_night ? navyCell("c tot", "se_night", y0, y1, tenths(t.se_night)) : "");
                });
                carried = grand;
                html += '<span class="nv sig" style="left:75%;top:85.6%;width:21%">' + esc(data.pilot.name) + "</span>";
                out.push({month: mo.month, html: '<section class="sheet navy">' + html + "</section>"});
            }
        });
        return out;
    };
    if (data.form === "navy") {
        const spreads = navySpreads();
        data.months = spreads.map((s) => data.months.find((mo) => mo.month === s.month));
        el("lb-sheets").innerHTML = spreads.map((s) => s.html).join("") ||
            '<p class="state-message">' + esc(i18n.t("logbook.empty")) + "</p>";
        // A long remark is written smaller, as a pilot squeezes it in, never cut.
        document.querySelectorAll(".sheet.navy .nv.rm").forEach((cell) => {
            let size = parseFloat(getComputedStyle(cell).fontSize);
            while (cell.scrollWidth > cell.clientWidth && size > 6) {
                size -= 0.5;
                cell.style.fontSize = size + "px";
            }
        });
    }
    const sheets = data.form === "navy" ? [] : data.months.map((mo, i) => {
        const head = data.form === "usaf" ? '<div class="form-title"><span>' + esc(TF("logbook.form.title")) + "</span>" +
                '<span class="form-no">' + esc(TF("logbook.form.form_no")) + "</span></div>"
            : '<div class="form-title book"><span>' + esc(TF("logbook.form.title")) + "</span></div>";
        // The grade as it stood that month, from the month's last sortie -
        // a promotion in May must not rewrite April's sheet.
        const grade = String((mo.rows.length && mo.rows[mo.rows.length - 1].rank) || data.pilot.rank || "").trim();
        const fields = [
            [TF("logbook.form.name"), data.form === "usaf" ? data.pilot.last + ", " + data.pilot.first : data.pilot.name],
            [TF("logbook.form.grade"), shortRank(grade), grade],
            [TF("logbook.form.organization"), data.organization],
            [TF("logbook.form.station"), mo.station],
            [TF("logbook.form.aircraft_type"), data.aircraft],
            [TF("logbook.form.month"), monthName(mo.month)],
        ];
        const rows = mo.rows.map((r) => "<tr>" +
            '<td class="num">' + r.day + "</td>" +
            "<td>" + esc(r.aircraft) + "</td>" +
            '<td class="mono">' + esc(r.code) + "</td>" +
            "<td>" + esc(r.mission) + "</td>" +
            '<td class="num">' + esc(r.takeoff) + "</td>" +
            '<td class="num">' + esc(r.landing) + "</td>" +
            '<td class="num">' + tenths(r.day_h) + "</td>" +
            '<td class="num">' + (r.night_h ? tenths(r.night_h) : "") + "</td>" +
            '<td class="num">' + tenths(r.hours) + "</td>" +
            '<td class="num">' + r.landings + "</td>" +
            '<td class="remarks">' + esc(remarks(r)) + "</td></tr>").join("");
        const totals = (label, t) => '<tr class="totals"><td colspan="6">' + esc(label) + "</td>" +
            '<td class="num">' + tenths(t.day) + "</td><td class=\"num\">" + (t.night ? tenths(t.night) : "") + "</td>" +
            '<td class="num">' + tenths(t.hours) + "</td><td class=\"num\">" + t.landings + "</td>" +
            "<td>" + esc(TF("logbook.form.summary", {sorties: t.sorties, air: t.air, ground: t.ground})) + "</td></tr>";
        return '<section class="sheet ' + esc(data.form) + '">' + head +
            '<div class="form-head">' + fields.map(([k, v, full]) =>
                '<div class="field"><span class="k">' + esc(k) + '</span><span class="v"' +
                (full && full !== v ? ' title="' + esc(full) + '"' : "") + ">" + esc(v) + "</span></div>").join("") + "</div>" +
            '<table class="form-table"><thead><tr>' +
                "<th>" + esc(TF("logbook.form.date")) + "</th><th>" + esc(TF("logbook.form.type")) + "</th>" +
                "<th>" + esc(TF("logbook.form.serial")) + "</th><th>" + esc(TF("logbook.form.mission")) + "</th>" +
                "<th>" + esc(TF("logbook.form.takeoff")) + "</th><th>" + esc(TF("logbook.form.landing")) + "</th>" +
                "<th>" + esc(TF("logbook.form.day")) + "</th><th>" + esc(TF("logbook.form.night")) + "</th>" +
                "<th>" + esc(TF("logbook.form.total")) + "</th><th>" + esc(TF("logbook.form.landings")) + "</th>" +
                "<th>" + esc(TF("logbook.form.remarks")) + "</th></tr></thead><tbody>" + rows + "</tbody><tfoot>" +
                totals(TF("logbook.form.total_month"), mo.totals) + totals(TF("logbook.form.total_to_date"), mo.to_date) +
            "</tfoot></table>" +
            '<div class="form-foot"><span class="certify">' + esc(TF("logbook.form.certify")) + "</span>" +
                '<span class="signature"><span class="sig-hand">' + esc(data.pilot.name) + "</span>" +
                    '<span class="line"></span>' + esc(data.pilot.name) + ", " + esc(grade) + "</span>" +
                '<span class="page">' + esc(TF("logbook.form.page", {n: i + 1, of: data.months.length})) + "</span></div>" +
            "</section>";
    });
    if (data.form !== "navy") {
        el("lb-sheets").innerHTML = sheets.join("") || '<p class="state-message">' + esc(i18n.t("logbook.empty")) + "</p>";
    }

    // On screen one sheet at a time, the current month first, the arrows
    // (and the keyboard's) turning the pages; print gets them all.
    const nodes = Array.from(document.querySelectorAll(".sheet"));
    let page = nodes.length - 1;
    const show = () => {
        nodes.forEach((n, i) => n.classList.toggle("current", i === page));
        el("lb-month").textContent = data.months[page] ? monthName(data.months[page].month) : "";
        el("lb-prev").disabled = page <= 0;
        el("lb-next").disabled = page >= nodes.length - 1;
    };
    if (nodes.length) {
        el("lb-pager").hidden = false;
        el("lb-prev").addEventListener("click", () => { if (page > 0) { page -= 1; show(); } });
        el("lb-next").addEventListener("click", () => { if (page < nodes.length - 1) { page += 1; show(); } });
        document.addEventListener("keydown", (e) => {
            if (e.key === "ArrowLeft") el("lb-prev").click();
            if (e.key === "ArrowRight") el("lb-next").click();
        });
    }
    if (nodes.length) { document.body.classList.add("paged"); show(); }
    done();
})();
