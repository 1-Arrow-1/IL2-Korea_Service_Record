/*
 * A Soviet pilot's personnel file (/api/ussr-file): a Russian document
 * throughout, like the USAF file is an English one.
 *
 *   1  личное дело (cover)              typed here
 *   2  послужной список                 typed here
 *   3  аттестация                       typed here
 *   4  выписки из приказов              typed here, two to a page, one per promotion
 *   5  орденская книжка                 cover, name page (with his photograph),
 *                                       award pages, last pages - pictures
 *   6  грамота Героя Советского Союза   a picture, for a Hero
 *   7  наградные листы                  the certificate page, embedded, per order
 *   8  биография                        the game's Russian text
 *   9  награды                          the shadowbox
 *
 * Every Russian line carries a tooltip in the reader's language.
 */
window.renderUssrFile = async function (ctx) {
    "use strict";
    const {data, el, esc, enc, careerId} = ctx;
    const S = data.strings;
    const p = data.pilot;
    const n = data.names;
    const tipAttr = PFC.tipAttr;
    document.documentElement.lang = "ru";
    document.title = S.cover_title.ru + " — " + n.last + " " + n.first;

    const label = (key, tag) => "<" + (tag || "span") + tipAttr(S[key].tip) + ">" + esc(S[key].ru) + "</" + (tag || "span") + ">";
    const line = (text, tip, cls) => '<p class="' + (cls || "") + '"' + tipAttr(tip) + ">" + esc(text) + "</p>";
    const pages = [];
    const page = (cls, html, part) => {
        pages.push('<section class="pf-page ussr ' + cls + '"' + (part ? ' data-part="' + part + '"' : "") + ">" + html + "</section>");
    };
    const field = (key, value, tip) => '<div class="pf-field"><span class="k"' + tipAttr(S[key].tip) + ">" + esc(S[key].ru) +
        '</span><span class="v"' + tipAttr(tip) + ">" + esc(value || " ") + "</span></div>";
    const photo = "/api/photo/" + enc(careerId) + "/" + enc(p.id) + "?avatar=" + enc(p.avatar || "") + "&h=512";
    const born = [data.birth_year, data.bio.born].filter(Boolean).join(", ");

    // 1 - личное дело
    page("portrait cover",
        '<div class="ussr-head">' + label("cover_title", "h1") + "</div>" +
        '<div class="pf-cover"><div class="pf-fields">' +
            field("label_surname", n.last, n.latin.split(" ").slice(-1)[0]) +
            field("label_first", n.first, n.latin.split(" ")[0]) +
            field("label_father", n.father) +
            field("label_rank", data.rank_ru, data.rank_tip) +
            field("label_post", data.post, data.post_tip) +
            field("label_unit", data.unit.short, data.unit_tip) +
            field("label_born", born, [data.born, data.bio_tip.born].filter(Boolean).join(", ")) +
            field("label_nationality", data.bio.nationality, data.bio_tip.nationality) +
            field("label_party", data.bio.party, data.bio_tip.party) +
            field("label_since", data.bio.since, data.bio_tip.since) +
        "</div>" +
        '<div class="pf-photo"><img alt="" src="' + photo + '" onerror="this.parentNode.style.visibility=\'hidden\'"></div></div>' +
        '<div class="pf-section pf-contents">' + label("contents", "h3") +
            '<table class="pf-table"><tbody id="pf-contents"></tbody></table></div>' +
        (["kia", "missing"].indexOf(p.state) >= 0
            ? '<img class="pf-stamp" src="/static/images/stamps/' + esc(p.state) + '.png" alt="">' : ""), "cover");

    // 2 - послужной список
    const rows = (cols, body) => '<table class="pf-table"><thead><tr>' + cols.map((c) => "<th>" + label(c) + "</th>").join("") +
        "</tr></thead><tbody>" + body + "</tbody></table>";
    const td = (text, tip, cls) => "<td" + (cls ? ' class="' + cls + '"' : "") + tipAttr(tip) + ">" + esc(text) + "</td>";
    page("portrait flow ussr-typed",
        '<div class="ussr-head">' + label("record_title", "h2") + "</div>" +
        '<div class="pf-section">' + label("record_ranks", "h3") + rows(["col_date", "col_rank", "col_order"],
            (data.extracts || []).map((x) => "<tr>" + td(x.date, x.tips.date, "date") +
                td((x.text.match(/«([^»]+)»/) || ["", ""])[1], x.tips.text) + td(x.number, x.tips.head) + "</tr>").join("")) + "</div>" +
        '<div class="pf-section">' + label("record_service", "h3") +
            line((data.start_date || "") + " — " + data.post + ", " + data.unit.short, data.post_tip + " · " + data.unit_tip) + "</div>" +
        '<div class="pf-section">' + label("record_battles", "h3") + line(data.bio.battles, data.bio_tip.battles) + "</div>" +
        '<div class="pf-section">' + label("record_awards", "h3") + rows(["col_date", "col_award", "col_number"],
            (data.record_awards || []).map((a) => "<tr>" + td(a.date_ru, a.date, "date") + td(a.name, a.name_tip) +
                td(a.number, "") + "</tr>").join("")) + "</div>" +
        '<div class="pf-section">' + label("record_combat", "h3") + '<table class="pf-table"><tbody>' +
            [["stat_sorties", p.sorties], ["stat_hours", p.flight_hours], ["stat_air", p.airborne], ["stat_ground", p.ground_targets]]
                .map(([k, v]) => "<tr>" + td(S[k].ru, S[k].tip) + '<td class="num">' + esc(v == null ? "" : v) + "</td></tr>").join("") +
        "</tbody></table></div>", "record");

    // 3 - аттестация
    const a = data.attestation;
    page("portrait flow ussr-typed",
        '<div class="ussr-head"><h2' + tipAttr(a.tips.title) + ">" + esc(a.title) + "</h2>" +
        line(a.subject, a.tips.subject, "sub") + line(a.period, a.tips.period, "sub") + "</div>" +
        '<table class="pf-table ussr-facts"><tbody>' + a.facts.map(([k, v, key]) =>
            "<tr>" + td(k, (S[key] || {}).tip) + td(v, "") + "</tr>").join("") + "</tbody></table>" +
        '<div class="ussr-text">' + a.lines.map((l) => line(l.ru, l.tip)).join("") +
            line(a.conclusion.ru, a.conclusion.tip, "conclusion") + "</div>" +
        '<div class="ussr-sign">' + line(a.commander, a.tips.commander) + '<span class="ussr-squiggle"></span>' +
            line(a.date, a.tips.date) + "</div>" +
        '<div class="ussr-sign">' + line(a.senior, a.tips.senior) + line(a.corps, a.tips.corps) + "</div>", "attestation");

    // 4 - выписки из приказов, two to a page
    const extract = (x) => '<div class="ussr-extract">' +
        line(x.head, x.tips.head, "head") + line(x.number + "  " + x.date, x.tips.number + " · " + x.tips.date, "num") +
        line(x.section, "", "sec") + line("§ 1", "", "sec") + line(x.text, x.tips.text, "text") +
        line(x.signed, x.tips.signed, "signed") +
        '<div class="ussr-certified">' + line(x.certified, x.tips.certified) + '<span class="ussr-squiggle"></span>' +
        '<img class="ussr-stamp" src="/static/images/certificates/ussr_seal.png" alt=""></div></div>';
    for (let i = 0; i < (data.extracts || []).length; i += 2) {
        page("portrait ussr-typed", data.extracts.slice(i, i + 2).map(extract).join('<hr class="ussr-cut">'), "orders");
    }

    // 5 - орденская книжка, 6 - грамота
    (data.images || []).forEach((im) => {
        const portrait = im.size[0] < im.size[1];
        page(portrait ? "portrait" : "landscape",
            '<div class="pf-centre">' + PFC.doc(im, portrait ? 726 : 996, portrait ? 966 : 756, photo) + "</div>", im.part);
    });

    // 7 - наградные листы, embedded
    (data.sheets || []).forEach((s) => page("portrait cert",
        '<div class="pf-centre"><div class="pf-fit" data-kind="cert"><iframe loading="eager" src="/certificate?embed=1&career=' +
        enc(careerId) + "&pilot=" + enc(p.id) + "&award=" + enc(s.type) + "&earned=" + enc(s.earned) +
        '" title=""></iframe></div></div>', "sheets"));

    // 8 - биография
    if ((data.biography || []).length) {
        const f = data.bio_fields || {};
        const fill = (s) => String(s || "").replace(/\$\[([^\]]+)\]/g, (whole, k) =>
            Object.prototype.hasOwnProperty.call(f, k) ? f[k] : whole);
        const said = data.biography_tips || [];
        page("portrait flow pf-bio ussr-bio", '<div class="ussr-head">' + label("biography_title", "h2") + "</div>" +
            data.biography.map((s, i) => /^#+\s/.test(s)
                ? "<h4" + tipAttr(said[i]) + ">" + esc(fill(s.replace(/^#+\s*/, ""))) + "</h4>"
                : "<p" + tipAttr(said[i]) + ">" + esc(fill(s)) + "</p>").join(""), "biography");
    }

    // 9 - награды: the shadowbox
    let box = null;
    try {
        const r = await fetch("/api/shadowbox/" + enc(careerId) + "?pilot=" + enc(p.id));
        if (r.ok) box = await r.json();
    } catch (_e) { box = null; }
    if (box) page("landscape", '<div class="pf-centre"><div class="pf-sbox" id="pf-sbox"></div></div>', "shadowbox");

    el("pf-doc").innerHTML = pages.join("");
    if (box) PFC.shadowbox(el("pf-sbox"), box);
    PFC.tooltips();

    // ready once the pictures are drawn and the embedded sheets settled
    const fits = Array.from(document.querySelectorAll(".pf-fit"));
    const imgs = Array.from(document.querySelectorAll(".pf-page img"));
    const total = fits.length + imgs.length;
    let done = 0;
    const status = () => {
        el("pf-status").textContent = done < total
            ? i18n.t("personnel.preparing", {done: done, total: total})
            : i18n.t("personnel.ready", {pages: document.querySelectorAll(".pf-page").length});
        el("pf-print").disabled = done < total;
    };
    const finish = () => { done += 1; status(); };
    imgs.forEach((im) => {
        if (im.complete) finish(); else { im.addEventListener("load", finish); im.addEventListener("error", finish); }
    });
    status();
    await Promise.all(fits.map((fit) => PFC.settle(fit).catch(() => {}).then(finish)));

    // the list of documents, counted now that sheets without a form have gone
    const counted = {};
    const order = [];
    document.querySelectorAll(".pf-page[data-part]").forEach((s) => {
        const part = s.dataset.part;
        if (part === "cover") return;
        if (order.indexOf(part) < 0) order.push(part);
        counted[part] = (counted[part] || 0) + 1;
    });
    el("pf-contents").innerHTML = order.map((x, i) => {
        const s = S["part_" + x] || {ru: x, tip: ""};
        return '<tr><td class="num">' + esc(i + 1) + ".</td><td" + tipAttr(s.tip) + ">" + esc(s.ru) + "</td></tr>";
    }).join("");
};
