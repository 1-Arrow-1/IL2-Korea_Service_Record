/*
 * The award's certificate. The American one is typed over a sheet: a
 * drawn template per decoration family (images/certificates/<family>.png,
 * 2200x1700, the ribbon and medal at the top, the seal below, the middle
 * band clear) when one exists, a plain parchment with the game's medal
 * otherwise. The text - country, establishing line, the decoration and its
 * cluster, the man, the reason, the deed, the date, the signature - is
 * always typed here, so a cluster never needs its own sheet. Soviet-pattern
 * awards get the decree instead. The certificate is an English document;
 * the decree follows the page's language.
 */
(async function () {
    "use strict";

    const el = (id) => document.getElementById(id);
    const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
        ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
    const q = new URLSearchParams(location.search);
    const careerId = q.get("career"), pilotId = q.get("pilot"), awardId = q.get("award"), earned = q.get("earned") || "";

    const settings = await fetch("/api/settings").then((r) => r.json()).catch(() => ({}));
    const override = (settings.overrides || []).find((o) => o.career === careerId);
    const pageLang = (override && override.language) || settings.language || "en";
    await i18n.init(pageLang);
    i18n.apply(document.body);
    el("ct-back").href = careerId ? "/#career/" + encodeURIComponent(careerId) : "/";
    el("ct-print").addEventListener("click", () => window.print());

    let data = null;
    try {
        if (!careerId || !pilotId || !awardId) throw new Error("missing");
        // The certificate reads in English; the decree in the page's language.
        // The certificate is an English document, the наградной лист a Russian
        // one: the record is read in that language for it.
        const country = String(awardId).slice(0, 3);
        const lang = country === "601" ? "en" : (country === "501" || country === "503") ? "ru" : pageLang;
        const r = await fetch("/api/citation/" + encodeURIComponent(careerId) + "/" + encodeURIComponent(pilotId) + "/" +
            encodeURIComponent(awardId) + "?earned=" + encodeURIComponent(earned) + "&lang=" + encodeURIComponent(lang));
        if (!r.ok) throw new Error(r.status);
        data = await r.json();
        if (!data || !data.certificate) throw new Error("none");
    } catch (err) {
        el("ct-state").textContent = i18n.t("certificate.failed"); el("ct-state").hidden = false;
        return;
    }
    const c = data.certificate;
    document.title = (c.title || c.to || "") + " — " + (c.name || c.subject || "");

    // A drawn sheet for this family, if the artist has made one.
    const family = data.family || "";
    const template = "/static/images/certificates/" + family + ".png";
    const decreeTemplate = "/static/images/certificates/decree_" + ({"501": "sov", "503": "dprk", "502": "prc"}[String(awardId).slice(0, 3)] || "sov") + ".png";
    // A drawn sheet brings its own shape: the page takes the picture's aspect.
    const exists = (url) => new Promise((ok) => {
        const im = new Image();
        im.onload = () => ok({w: im.naturalWidth, h: im.naturalHeight});
        im.onerror = () => ok(null);
        im.src = url;
    });

    if (c.form === "usaf") {
        const drawn = await exists(template);
        const portrait = drawn && drawn.h > drawn.w;
        const style = drawn ? ' style="background-image:url(\'' + template + '\');aspect-ratio:' + drawn.w + ' / ' + drawn.h + '"' : "";
        const line = (cls, text) => text ? '<div class="' + cls + '">' + esc(text) + "</div>" : "";
        const nameBlock = line("ct-to", c.to) + line("ct-recipient", c.name) + line("ct-unit", c.unit_line) + line("ct-service", c.service);
        el("ct-sheet").innerHTML =
            '<section class="sheet usaf ' + esc(family) + (drawn ? " drawn" : "") + (portrait ? " portrait" : "") + '"' + style + ">" +
                (drawn ? "" : '<img class="ct-medal" src="' + esc(data.icon) + '" alt="">') +
                '<div class="ct-text">' +
                    line("ct-country", c.header) +
                    (c.pre || []).map((t) => line("ct-pre", t)).join("") +
                    (c.name_first ? nameBlock : "") +
                    line("ct-name", c.title) +
                    line("ct-cluster", c.cluster) +
                    (c.sub || []).map((t) => line("ct-sub", t)).join("") +
                    (c.name_first ? "" : nameBlock) +
                    '<div class="ct-for' + (c.for && !c.for.endsWith(":") ? " centred" : "") + '">' +
                        (c.for ? '<span class="ct-for-label">' + esc(c.for) + "</span> " : "") + esc(c.reason) + "</div>" +
                    line("ct-where", c.where) +
                    line("ct-deed", c.deed) +
                    (Array.isArray(c.close) ? c.close : [c.close]).map((t) => line("ct-close", t)).join("") +
                    '<div class="ct-given-block">' + (c.given || []).map((t) => line("ct-given", t)).join("") + "</div>" +
                "</div>" +
                (drawn ? "" :
                    '<div class="ct-seal"><svg viewBox="0 0 100 100"><circle cx="50" cy="50" r="46"/><circle cx="50" cy="50" r="38"/>' +
                    '<path d="M50 22l7.6 16.2 17.8 2.2-13.1 12.3 3.4 17.6L50 61.6l-15.7 8.7 3.4-17.6-13.1-12.3 17.8-2.2z"/></svg></div>') +
                (c.signers || [{}, {name: c.signer, title: c.signer_title}]).map((s, i) => s && s.name ?
                    '<div class="ct-signature ' + (i === 0 ? "left" : "right") + '">' +
                    (s.image ? '<img class="ct-sign-image" src="' + esc(s.image) + '" alt="' + esc(s.name) + '">' : '<span class="ct-sign">' + esc(s.name) + "</span>") +
                    '<span class="ct-sign-line"></span>' +
                    '<span class="ct-sign-title">' + esc(s.title) + "</span></div>" : "").join("") +
            "</section>";
    } else if (c.form === "nagradnoy") {
        // The award sheet: typed onto the printed form along its rules, in
        // a hand, as the originals were filled.
        const form = "/static/images/certificates/nagradnoy_list.png";
        const drawn = await exists(form);
        // Each entry carries its meaning as a tooltip, in the page's language.
        const tr = c.translation || {};
        const tip = (cls) => {
            const k = cls.replace("nl-", ""); let t = i18n.t("certificate.sheet." + k);
            if (!t || t.startsWith("certificate.")) return "";
            const v = tr[k] || (k === "name" ? c.name : k === "rank" ? c.rank : k === "born" ? c.born : k === "sign" ? c.commander_name : k === "commissar" ? c.commissar : "");
            return ' title="' + esc(t + (v ? ": " + v : "")) + '"';
        };
        const f = (cls, text) => text ? '<div class="nl ' + cls + '"' + tip(cls) + ">" + esc(text) + "</div>" : "";
        const deedLines = [];
        (c.deed || []).concat([c.conclusion]).forEach((par) => { if (par) deedLines.push(par); });
        el("ct-sheet").innerHTML =
            '<section class="sheet nagradnoy' + (drawn ? " drawn" : "") + '"' + (drawn ? ' style="background-image:url(\'' + form + '\');aspect-ratio:' + drawn.w + ' / ' + drawn.h + '"' : "") + ">" +
                f("nl-name", c.name) + f("nl-rank", c.rank) + f("nl-post", c.post) + f("nl-to", c.to) +
                f("nl-born", c.born) + f("nl-nationality", c.nationality) + f("nl-since", c.since) + f("nl-party", c.party) +
                f("nl-battles", c.battles) + f("nl-wounds", c.wounds) + f("nl-held", c.held) + f("nl-rvk", c.birthplace ? c.birthplace + " (по месту рождения)" : "") +
                '<div class="nl nl-deed"' + tip("nl-deed") + ">" + deedLines.map((t) => "<p>" + esc(t) + "</p>").join("") + "</div>" +
                '<div class="nl nl-sign"' + tip("nl-sign") + '><span class="ct-sign">' + esc(c.commander_name) + "</span></div>" +
                (c.commissar ? '<div class="nl nl-commissar"' + tip("nl-commissar") + '><span class="ct-sign">' + esc(c.commissar) + "</span></div>" : "") +
                f("nl-date", c.date) +
                '<img class="nl-seal" src="/static/images/certificates/ussr_seal.png" alt="">' +
            "</section>";
    } else {
        const drawn = await exists(decreeTemplate);
        el("ct-sheet").innerHTML =
            '<section class="sheet decree' + (drawn ? " drawn" : "") + '"' + (drawn ? ' style="background-image:url(\'' + decreeTemplate + '\')"' : "") + ">" +
                (drawn ? "" : '<img class="ct-medal small" src="' + esc(data.icon) + '" alt="">') +
                '<div class="ct-text">' +
                    '<div class="ct-title">' + esc(c.title) + "</div>" +
                    '<div class="ct-subject">' + esc(c.subject) + "</div>" +
                    (c.paragraphs || []).map((p) => '<p class="ct-para">' + esc(p) + "</p>").join("") +
                    '<div class="ct-place">' + esc(c.place) + (c.date ? ", " + esc(c.date) : "") + "</div>" +
                    '<div class="ct-signers">' + (c.signers || []).map((s) =>
                        '<div class="ct-signer"><span class="ct-sign">' + esc(s[0]) + '</span><span class="ct-sign-title">' + esc(s[1]) + "</span></div>").join("") + "</div>" +
                "</div>" +
            "</section>";
    }
})();
