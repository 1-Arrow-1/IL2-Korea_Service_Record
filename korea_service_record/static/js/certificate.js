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
        const country = String(awardId).slice(0, 3);
        const lang = country === "601" ? "en" : pageLang;
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
    document.title = (c.name || c.title || "") + " — " + (c.recipient || "");

    // A drawn sheet for this family, if the artist has made one.
    const family = data.family || "";
    const template = "/static/images/certificates/" + family + ".png";
    const decreeTemplate = "/static/images/certificates/decree_" + ({"501": "sov", "503": "dprk", "502": "prc"}[String(awardId).slice(0, 3)] || "sov") + ".png";
    const exists = (url) => new Promise((ok) => { const im = new Image(); im.onload = () => ok(true); im.onerror = () => ok(false); im.src = url; });

    if (c.form === "usaf") {
        const drawn = await exists(template);
        el("ct-sheet").innerHTML =
            '<section class="sheet usaf' + (drawn ? " drawn" : "") + '"' + (drawn ? ' style="background-image:url(\'' + template + '\')"' : "") + ">" +
                (drawn ? "" : '<img class="ct-medal" src="' + esc(data.icon) + '" alt="">') +
                '<div class="ct-text">' +
                    '<div class="ct-country">' + esc(c.country) + "</div>" +
                    '<div class="ct-established">' + esc(c.established) + "</div>" +
                    '<div class="ct-name">' + esc(c.name) + "</div>" +
                    (c.cluster ? '<div class="ct-cluster">' + esc(c.cluster) + "</div>" : "") +
                    '<div class="ct-to">' + esc(c.to) + "</div>" +
                    '<div class="ct-recipient">' + esc(c.recipient) + "</div>" +
                    (c.service ? '<div class="ct-service">' + esc(c.service) + "</div>" : "") +
                    '<div class="ct-for"><span class="ct-for-label">' + esc(c.for) + "</span> " + esc(c.reason) + "</div>" +
                    (c.deed ? '<div class="ct-deed">' + esc(c.deed) + "</div>" : "") +
                    '<div class="ct-given">' + esc(c.given) + "</div>" +
                    '<div class="ct-on">' + esc(c.on) + "</div>" +
                "</div>" +
                (drawn ? "" :
                    '<div class="ct-seal"><svg viewBox="0 0 100 100"><circle cx="50" cy="50" r="46"/><circle cx="50" cy="50" r="38"/>' +
                    '<path d="M50 22l7.6 16.2 17.8 2.2-13.1 12.3 3.4 17.6L50 61.6l-15.7 8.7 3.4-17.6-13.1-12.3 17.8-2.2z"/></svg></div>') +
                '<div class="ct-signature"><span class="ct-sign">' + esc(c.signer) + '</span><span class="ct-sign-line"></span>' +
                    '<span class="ct-sign-title">' + esc(c.signer_title) + "</span></div>" +
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
