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

    const el = (id) => document.getElementById(id);
    const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
        ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
    const params = new URLSearchParams(location.search);
    const careerId = params.get("career");
    const pilotId = params.get("pilot");

    const settings = await fetch("/api/settings").then((r) => r.json()).catch(() => ({}));
    const override = (settings.overrides || []).find((o) => o.career === careerId);
    const pageLang = (override && override.language) || settings.language || "en";
    await i18n.init(pageLang);
    i18n.apply(document.body);
    el("lb-back").href = careerId ? "/#career/" + encodeURIComponent(careerId) : "/";
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
        return;
    }

    // The form's language: the document's own where it has one.
    const formLang = {usaf: "en", sov: "ru"}[data.form] || pageLang;
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

    const sheets = data.months.map((mo, i) => {
        const head = data.form === "usaf" ? '<div class="form-title"><span>' + esc(TF("logbook.form.title")) + "</span>" +
                '<span class="form-no">' + esc(TF("logbook.form.form_no")) + "</span></div>"
            : '<div class="form-title book"><span>' + esc(TF("logbook.form.title")) + "</span></div>";
        // The grade as it stood that month, from the month's last sortie -
        // a promotion in May must not rewrite April's sheet.
        const grade = (mo.rows.length && mo.rows[mo.rows.length - 1].rank) || data.pilot.rank;
        const fields = [
            [TF("logbook.form.name"), data.form === "usaf" ? data.pilot.last + ", " + data.pilot.first : data.pilot.name],
            [TF("logbook.form.grade"), grade],
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
            '<div class="form-head">' + fields.map(([k, v]) =>
                '<div class="field"><span class="k">' + esc(k) + '</span><span class="v">' + esc(v) + "</span></div>").join("") + "</div>" +
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
                '<span class="signature"><span class="line"></span>' + esc(data.pilot.name) + ", " + esc(grade) + "</span>" +
                '<span class="page">' + esc(TF("logbook.form.page", {n: i + 1, of: data.months.length})) + "</span></div>" +
            "</section>";
    });
    el("lb-sheets").innerHTML = sheets.join("") || '<p class="state-message">' + esc(i18n.t("logbook.empty")) + "</p>";

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
})();
