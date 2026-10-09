/*
 * A Chinese pilot's personnel file (/api/prc-file): a Chinese document
 * throughout, like the USAF file is an English one.
 *
 *   1  cadre record (幹部履歷表)        drawn here
 *   2  record of merits and awards     drawn here
 *   3  merit booklet (立功證明書)       cover, inside spread, further forms two to a page
 *   4  award certificates (獎狀)       First and Special Class merits
 *   5  Combat Hero                     the medal, one page per class
 *   6  decorations (獎章)              every medal he holds
 *   7  biography (簡歷)
 *
 * Everything Chinese carries a tooltip in the reader's language: on the
 * documents a region per field (template pixels from the server), on the
 * typeset pages the element itself, in the biography each paragraph.
 * Tooltips are for the screen only.
 */
window.renderPrcFile = function (ctx) {
    "use strict";
    const {data, el, esc, enc, careerId} = ctx;
    const S = data.strings;
    const p = data.pilot;
    const prof = data.profile;
    document.documentElement.lang = "zh-Hant";
    document.title = S.cover_title.zh + " — " + (data.name_zh || p.name);

    const tipAttr = PFC.tipAttr;
    const doc = PFC.doc;
    const zh =(key, tag) => "<" + (tag || "span") + tipAttr(S[key].tip) + ">" + esc(S[key].zh) + "</" + (tag || "span") + ">";
    const pages = [];
    const page = (cls, html, part) => {
        pages.push('<section class="pf-page prc ' + cls + '"' + (part ? ' data-part="' + part + '"' : "") + ">" + html + "</section>");
    };
    const field = (key, value, tip) => '<div class="pf-field"><span class="k"' + tipAttr(S[key].tip) + ">" + esc(S[key].zh) +
        '</span><span class="v"' + tipAttr(tip) + ">" + esc(value || "　") + "</span></div>";
    const t = prof.tips;

    // 1 - cadre record
    page("portrait cover",
        '<div class="prc-head">' + zh("cover_title", "h1") + "</div>" +
        '<div class="pf-cover"><div class="pf-fields">' +
            field("label_name", data.name_zh, t.name) +
            field("label_sex", prof.sex, t.sex) +
            field("label_born", data.born_zh, data.born) +
            field("label_native", [prof.province && prof.province + "省", prof.county].filter(Boolean).join(" "), t.native) +
            field("label_family", prof.family, t.family) +
            field("label_status", prof.status, t.status) +
            field("label_enlisted", prof.enlisted, t.enlisted) +
            field("label_party", prof.party, t.party) +
            field("label_unit", data.unit_zh, data.unit_tip) +
            field("label_post", data.post_now, data.post_now_tip) +
        "</div>" +
        '<div class="pf-photo"><img alt="" src="/api/photo/' + enc(careerId) + "/" + enc(p.id) +
            "?avatar=" + enc(p.avatar || "") + '&h=512" onerror="this.parentNode.style.visibility=\'hidden\'"></div></div>' +
        '<div class="pf-section pf-contents">' + zh("contents", "h3") +
            '<table class="pf-table"><tbody id="pf-contents"></tbody></table></div>' +
        (["kia", "missing"].indexOf(p.state) >= 0
            ? '<img class="pf-stamp" src="/static/images/stamps/' + esc(p.state) + '.png" alt="">' : ""), "cover");

    // 2 - record of merits and awards, and the combat record
    page("portrait flow",
        '<div class="prc-head">' + zh("record_title", "h2") + "</div>" +
        '<div class="pf-section"><table class="pf-table"><thead><tr><th>' + zh("col_date") + "</th><th>" + zh("col_award") +
        "</th></tr></thead><tbody>" +
        // one row per merit grade, its latest awarding; the earlier ones beneath
        (data.record || []).map((r) => '<tr><td class="date"' + tipAttr(r.date) + ">" + esc(r.date_zh) + "</td><td>" +
            "<span" + tipAttr(r.name_tip) + ">" + esc(r.name_zh) + "</span>" +
            ((r.earlier || []).length ? '<ul class="pf-earlier">' + r.earlier.slice().reverse().map((e) =>
                "<li" + tipAttr(e.name_tip + " · " + e.date) + '><span class="date">' + esc(e.date_zh) + "</span> " +
                esc(e.name_zh) + "</li>").join("") + "</ul>" : "") + "</td></tr>").join("") +
        "</tbody></table></div>" +
        '<div class="pf-section">' + zh("combat_title", "h3") + '<table class="pf-table"><tbody>' +
        [["stat_sorties", p.sorties], ["stat_hours", p.flight_hours], ["stat_air", p.airborne],
         ["stat_ground", p.ground_targets]].map(([k, v]) =>
            "<tr><td" + tipAttr(S[k].tip) + ">" + esc(S[k].zh) + '</td><td class="num">' + esc(v == null ? "" : v) + "</td></tr>").join("") +
        "</tbody></table></div>", "record");

    // 3 - the merit booklet: cover, spread, then the further forms two to a page
    const images = data.images || [];
    const booklet = images.filter((im) => im.part === "booklet");
    if (booklet.length) {
        page("portrait", '<div class="pf-centre">' + doc(booklet[0], 726, 966) + "</div>", "booklet");
        page("landscape", '<div class="pf-centre">' + doc(booklet[1], 996, 756) + "</div>", "booklet");
        const pairs = booklet.slice(2);
        for (let i = 0; i < pairs.length; i += 2) {
            page("landscape", '<div class="pf-centre prc-pair">' + pairs.slice(i, i + 2).reverse()
                .map((im) => doc(im, 490, 756)).join("") + "</div>", "booklet");
        }
    }
    // 4 - award certificates
    images.filter((im) => im.part === "certs").forEach((im) =>
        page("landscape", '<div class="pf-centre">' + doc(im, 996, 756) + "</div>", "certs"));

    // 5 - Combat Hero: the medal, its class, the day
    (data.heroes || []).forEach((h) => page("portrait",
        '<div class="pf-centre prc-hero">' +
        '<img class="prc-hero-medal" src="/static/images/certificates/prc_hero_' + esc(h.cls) + '.webp" alt=""' +
            tipAttr(h.tip_title) + ">" +
        '<div class="prc-hero-title"' + tipAttr(h.tip_title) + ">" + esc(h.title_zh) + "</div>" +
        '<div class="prc-hero-name"' + tipAttr(p.name) + ">" + esc(h.name || p.name) + "</div>" +
        '<div class="prc-hero-date"' + tipAttr(h.tip_date) + ">" + esc(h.date_zh) + "</div>" +
        '<div class="prc-hero-by"' + tipAttr(h.tip_by) + ">" + esc(S.hero_by.zh) + "</div></div>", "heroes"));

    // 6 - decorations
    if ((data.medals || []).length) {
        page("portrait", '<div class="prc-head">' + zh("medals_title", "h2") + '</div><div class="prc-medals">' +
            data.medals.map((m) => '<figure' + tipAttr(m.name_tip) + '><img src="/api/icon/award/' + enc(m.type) +
                '?h=260" alt=""><figcaption>' + esc(m.name_zh) + "</figcaption></figure>").join("") + "</div>", "medals");
    }

    // 7 - biography
    if ((data.biography || []).length) {
        const f = data.bio_fields || {};
        const fill = (s) => String(s || "").replace(/\$\[([^\]]+)\]/g, (whole, k) =>
            Object.prototype.hasOwnProperty.call(f, k) ? f[k] : whole);
        const said = data.biography_tips || [];
        page("portrait flow pf-bio prc-bio", '<div class="prc-head">' + zh("biography_title", "h2") + "</div>" +
            data.biography.map((s, i) => /^#+\s/.test(s)
                ? "<h4" + tipAttr(said[i]) + ">" + esc(fill(s.replace(/^#+\s*/, ""))) + "</h4>"
                : "<p" + tipAttr(said[i]) + ">" + esc(fill(s)) + "</p>").join(""), "biography");
    }

    el("pf-doc").innerHTML = pages.join("");

    // contents
    const counted = {};
    const order = [];
    document.querySelectorAll(".pf-page[data-part]").forEach((s) => {
        const part = s.dataset.part;
        if (part === "cover") return;
        if (order.indexOf(part) < 0) order.push(part);
        counted[part] = (counted[part] || 0) + 1;
    });
    el("pf-contents").innerHTML = order.map((x, i) => {
        const s = S["part_" + x];
        return '<tr><td class="num">' + esc(i + 1) + ".</td><td" + tipAttr(s.tip) + ">" + esc(s.zh) + "</td></tr>";
    }).join("");

    PFC.tooltips();

    // ready once the documents are drawn
    const imgs = Array.from(document.querySelectorAll(".pf-page img"));
    const total = imgs.length;
    let done = 0;
    const status = () => {
        el("pf-status").textContent = done < total
            ? i18n.t("personnel.preparing", {done: done, total: total})
            : i18n.t("personnel.ready", {pages: document.querySelectorAll(".pf-page").length});
        el("pf-print").disabled = done < total;
    };
    imgs.forEach((im) => {
        const finish = () => { done += 1; status(); };
        if (im.complete) finish(); else { im.addEventListener("load", finish); im.addEventListener("error", finish); }
    });
    status();
};
