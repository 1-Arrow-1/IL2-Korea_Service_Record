/*
 * A USAF pilot's personnel file, one printable document (/personnel?career=&pilot=):
 *
 *   1  cover sheet                 drawn here
 *   2  service record              drawn here
 *   3  promotion certificates      /api/promotion-certificate, a picture each
 *   4  award certificates          the certificate page, embedded, one each
 *   5  biography                   drawn here, from /api/personnel
 *   6  flight record               the AF Form 5 page, embedded, two months a page
 *   7  shadowbox                   laid out here from /api/shadowbox
 *
 * Embedded pages are drawn at their own design width and scaled down as a
 * whole, so they print exactly as they look on their own. The file is an
 * English document, like the Form 5; the bar above it follows the reader.
 * Strings: personnel.* (the bar) and personnel.form.* (the file, from the
 * English bundle).
 */
(async function () {
    "use strict";

    const el = (id) => document.getElementById(id);
    const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
        ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
    const q = new URLSearchParams(location.search);
    const careerId = q.get("career"), pilotId = q.get("pilot");
    const enc = encodeURIComponent;

    const settings = await fetch("/api/settings").then((r) => r.json()).catch(() => ({}));
    const override = (settings.overrides || []).find((o) => o.career === careerId);
    const pageLang = (override && override.language) || settings.language || "en";
    await i18n.init(pageLang);
    i18n.apply(document.body);
    if (pageLang !== "en") await i18n.load("en");
    const bundle = i18n.loaded.en || i18n.loaded[pageLang];
    const TF = (key, p) => {
        let text = i18n._lookup(bundle, key);
        if (text === null) text = i18n.t(key, p);
        else if (p) text = text.replace(/\{(\w+)\}/g, (m, n) => (n in p ? String(p[n]) : m));
        return text;
    };

    const back = el("pf-back");
    back.href = careerId ? "/#career/" + enc(careerId) : "/";
    back.addEventListener("click", (event) => {
        // Opened by the Service Record: return to that tab and close this one.
        const parent = window.opener;
        if (!parent || parent.closed) { return; }
        event.preventDefault();
        const href = back.href;
        try {
            parent.location.href = href;
            parent.focus();
            window.close();
            setTimeout(() => { if (!window.closed) { window.location.href = href; } }, 100);
        } catch (_error) {
            window.location.href = href;
        }
    });
    el("pf-print").addEventListener("click", () => window.print());

    const fail = () => {
        el("pf-state").textContent = i18n.t("personnel.failed");
        el("pf-state").hidden = false;
        el("pf-status").textContent = "";
    };
    let data, logbook;
    try {
        if (!careerId || !pilotId) throw new Error("missing");
        const [a, b] = await Promise.all([
            fetch("/api/personnel/" + enc(careerId) + "/" + enc(pilotId)),
            fetch("/api/logbook/" + enc(careerId) + "/" + enc(pilotId)),
        ]);
        if (!a.ok) {
            // Not a USAF pilot: a Chinese, Soviet or North Korean one has a file of his own.
            for (const [api, render] of [["prc-file", window.renderPrcFile], ["ussr-file", window.renderUssrFile],
                                         ["dprk-file", window.renderDprkFile]]) {
                if (a.status !== 404) break;
                const c = await fetch("/api/" + api + "/" + enc(careerId) + "/" + enc(pilotId) + "?lang=" + enc(pageLang));
                if (c.ok) {
                    await render({data: await c.json(), el: el, esc: esc, enc: enc, careerId: careerId});
                    return;
                }
            }
            throw new Error(a.status);
        }
        data = await a.json();
        logbook = b.ok ? await b.json() : {months: []};
    } catch (err) {
        fail();
        return;
    }
    const p = data.pilot;
    document.documentElement.lang = "en";
    document.title = TF("personnel.form.title") + " — " + p.name;

    const longDate = (raw) => {
        const parts = String(raw || "").split(/[.\-/]/).map(Number);
        if (parts.length < 3 || !parts[0]) { return raw || ""; }
        return new Intl.DateTimeFormat("en-US", {day: "numeric", month: "long", year: "numeric"})
            .format(new Date(parts[0], parts[1] - 1, parts[2]));
    };
    const field = (key, value) => '<div class="pf-field"><span class="k">' + esc(TF("personnel.form." + key)) +
        '</span><span class="v">' + esc(value) + "</span></div>";
    const head = (title) => '<div class="pf-form-head"><div class="dept">' + esc(TF("personnel.form.department")) +
        '</div><div class="title">' + esc(title) + '</div><div class="sub">' + esc(TF("personnel.form.service")) + "</div></div>" +
        '<hr class="pf-rule">';
    const foot = (n) => '<div class="pf-foot"><span>' + esc(p.name) + " · " + esc(data.squadron) + "</span><span>" +
        esc(TF("personnel.form.page", {n: n})) + "</span></div>";
    const pages = [];
    const page = (cls, html, part) => {
        pages.push('<section class="pf-page ' + cls + '"' + (part ? ' data-part="' + part + '"' : "") + ">" + html + "</section>");
    };
    const state = {kia: "status_kia", missing: "status_missing", wounded: "status_wounded", pow: "status_pow"}[p.state] || "status_active";
    const startRank = (data.biography && data.biography.pilot && data.biography.pilot.starting_rank) || "";

    // 1 - cover sheet
    const lastFirst = (p.name || "").split(" ").length > 1
        ? p.name.split(" ").slice(-1)[0] + ", " + p.name.split(" ").slice(0, -1).join(" ") : p.name;
    page("portrait cover",
        head(TF("personnel.form.title")) +
        '<div class="pf-cover"><div class="pf-fields">' +
            field("name", lastFirst) + field("grade", p.rank) + field("organization", data.squadron) +
            field("born", longDate(p.birth_date)) +
            field("entered", longDate(data.start_date) + (startRank ? " · " + startRank : "")) +
            field("status", TF("personnel.form." + state) + " · " + TF("personnel.form.as_of", {date: longDate(data.current_date)})) +
        "</div>" +
        '<div class="pf-photo"><img alt="" src="/api/photo/' + enc(careerId) + "/" + enc(p.id) +
            "?avatar=" + enc(p.avatar || "") + '&h=512" onerror="this.parentNode.style.visibility=\'hidden\'"></div></div>' +
        '<div class="pf-section pf-contents"><h3>' + esc(TF("personnel.form.contents")) + "</h3>" +
            '<table class="pf-table"><tbody id="pf-contents"></tbody></table></div>' +
        (["kia", "missing"].indexOf(p.state) >= 0
            ? '<img class="pf-stamp" src="/static/images/stamps/' + esc(p.state) + '.png" alt="">' : "") +
        foot(1), "cover");

    // 2 - service record
    const promos = [{date: data.start_date, rank: startRank, entered: true}].concat(data.promotions || []);
    page("portrait flow",
        head(TF("personnel.form.record_title")) +
        '<div class="pf-section"><h3>' + esc(TF("personnel.form.promotions")) + "</h3>" +
        '<table class="pf-table"><thead><tr><th>' + esc(TF("personnel.form.col_date")) + "</th><th>" +
            esc(TF("personnel.form.col_grade")) + "</th></tr></thead><tbody>" +
        promos.filter((r) => r.rank).map((r) => '<tr><td class="date">' + esc(r.date) + "</td><td>" + esc(r.rank) +
            (r.entered ? " — " + esc(TF("personnel.form.entered_short")) : "") + "</td></tr>").join("") +
        "</tbody></table></div>" +
        '<div class="pf-section"><h3>' + esc(TF("personnel.form.assignments")) + "</h3>" +
        '<table class="pf-table"><tbody><tr><td class="date">' + esc(data.start_date) + "</td><td>" + esc(data.squadron) +
        "</td></tr></tbody></table></div>" +
        '<div class="pf-section"><h3>' + esc(TF("personnel.form.combat")) + "</h3>" +
        '<table class="pf-table"><tbody>' +
        [["sorties", p.sorties], ["flight_hours", p.flight_hours], ["air_victories", p.airborne],
         ["ground_targets", p.ground_targets], ["awards", data.grants_total || 0]].map(([k, v]) =>
            "<tr><td>" + esc(TF("personnel.form." + k)) + '</td><td class="num">' + esc(v) + "</td></tr>").join("") +
        "</tbody></table></div>" +
        '<div class="pf-section"><h3>' + esc(TF("personnel.form.decorations")) + "</h3>" +
        '<table class="pf-table"><thead><tr><th>' + esc(TF("personnel.form.col_date")) + "</th><th>" +
            esc(TF("personnel.form.col_decoration")) + "</th></tr></thead><tbody>" +
        // One row per decoration as he wears it; under it the earlier awards
        // of that ladder with the citation each came with. Their own
        // certificates are left out of the file - the sheet behind is for
        // the decoration as it stands.
        (data.decorations || []).map((g) => '<tr class="pf-dec"><td class="date">' + esc(g.earned) + "</td><td>" + esc(g.name) +
            ((g.earlier || []).length ? '<ul class="pf-earlier">' + g.earlier.map((e) =>
                '<li><span class="date">' + esc(e.earned) + "</span> " + esc(e.name) +
                (e.citation ? '<span class="pf-cite">' + esc(e.citation) + "</span>" : "") + "</li>").join("") + "</ul>" : "") +
            "</td></tr>").join("") +
        "</tbody></table></div>", "record");

    // 3 - promotion certificates: pictures from the server
    (data.promotions || []).forEach((pr, i) => page("portrait",
        '<div class="pf-centre"><img class="pf-cert-img" alt="" src="/api/promotion-certificate/' + enc(careerId) +
        "/" + enc(p.id) + "/" + enc(pr.rank_id) + '"></div>', "promotions"));

    // 4 - award certificates: the certificate page, embedded, one each.
    // Its orientation is only known once it is drawn; the page is portrait
    // until then and turns landscape if the sheet is.
    (data.decorations || []).forEach((g) => page("portrait cert",
        '<div class="pf-centre"><div class="pf-fit" data-kind="cert"><iframe loading="eager" src="/certificate?embed=1&career=' +
        enc(careerId) + "&pilot=" + enc(p.id) + "&award=" + enc(g.type) + "&earned=" + enc(g.earned) +
        '" title=""></iframe></div></div>', "awards"));

    // 5 - biography
    const bio = data.biography;
    if (bio && bio.paragraphs && bio.paragraphs.length) {
        const fields = {name: bio.pilot.name, firstName: bio.pilot.first_name, lastName: bio.pilot.last_name,
                        birthDate: longDate(bio.pilot.birth_date), startRank: bio.pilot.starting_rank};
        const fill = (t) => String(t || "").replace(/\$\[([^\]]+)\]/g, (whole, k) =>
            Object.prototype.hasOwnProperty.call(fields, k) ? fields[k] : whole);
        page("portrait flow pf-bio",
            head(TF("personnel.form.biography")) +
            "<h2>" + esc(TF("personnel.form.biography")) + '</h2><div class="who">' + esc(bio.pilot.name) + "</div>" +
            bio.paragraphs.map((t) => /^#+\s/.test(t)
                ? "<h4>" + esc(fill(t.replace(/^#+\s*/, ""))) + "</h4>"
                : "<p>" + esc(fill(t)) + "</p>").join(""), "biography");
    }

    // 6 - flight record: two months to a portrait page
    const months = (logbook.months || []).map((m) => m.month);
    for (let i = 0; i < months.length; i += 2) {
        page("portrait", months.slice(i, i + 2).map((m) =>
            '<div class="pf-half"><div class="pf-fit" data-kind="logbook"><iframe loading="eager" src="/logbook?embed=1&career=' +
            enc(careerId) + "&pilot=" + enc(p.id) + "&month=" + enc(m) + '" title=""></iframe></div></div>').join(""),
            "logbook");
    }

    // 7 - shadowbox
    let box = null;
    try {
        const r = await fetch("/api/shadowbox/" + enc(careerId) + "?pilot=" + enc(p.id));
        if (r.ok) box = await r.json();
    } catch (_e) { box = null; }
    if (box) page("landscape", '<div class="pf-centre"><div class="pf-sbox" id="pf-sbox"></div></div>', "shadowbox");

    el("pf-doc").innerHTML = pages.join("");

    if (box) PFC.shadowbox(el("pf-sbox"), box);

    // Wait for each embedded page, then scale it into its box.
    const fits = Array.from(document.querySelectorAll(".pf-fit"));
    const total = fits.length;
    let finished = 0;
    const status = () => {
        el("pf-status").textContent = finished < total
            ? i18n.t("personnel.preparing", {done: finished, total: total})
            : i18n.t("personnel.ready", {pages: document.querySelectorAll(".pf-page").length});
        el("pf-print").disabled = finished < total;
    };
    status();
    await Promise.all(fits.map((fit) => PFC.settle(fit).catch(() => {}).then(() => { finished += 1; status(); })));
    // The contents, counted now that awards without a certificate have
    // gone: how many commissions, certificates and flight-record months.
    const counted = {promotions: 0, awards: 0};
    const order = [];
    document.querySelectorAll(".pf-page[data-part]").forEach((s) => {
        const part = s.dataset.part;
        if (order.indexOf(part) < 0) order.push(part);
        if (part in counted) counted[part] += 1;
    });
    const many = {promotions: counted.promotions, awards: counted.awards,
                  logbook: document.querySelectorAll(".pf-half").length};
    el("pf-contents").innerHTML = order.filter((x) => x !== "cover").map((x, i) =>
        '<tr><td class="num">' + (i + 1) + ".</td><td>" + esc(TF("personnel.form.part_" + x)) +
        (x in many ? " (" + many[x] + ")" : "") + "</td></tr>").join("");
    status();
})();
