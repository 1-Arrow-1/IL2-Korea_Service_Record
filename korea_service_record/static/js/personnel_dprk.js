/*
 * A North Korean pilot's personnel file (/api/dprk-file): Korean throughout.
 *
 *   1  간부리력서 (cadre record)        typed here
 *   2  복무경력 (record of service)     typed here
 *   3  훈장증 (order booklets)          one per order: cover, personal page, award page
 *   4  표창장                           the Presidium's certificate, for a Hero
 *   6  수훈 제의서                      the nomination sheets, embedded
 *   7  자서전                           the game's text in the reader's language: the game has no Korean
 *   8  훈장함                           the shadowbox
 *
 * Every Korean line carries a tooltip in the reader's language.
 */
window.renderDprkFile = async function (ctx) {
    "use strict";
    const {data, el, esc, enc, careerId} = ctx;
    const S = data.strings;
    const p = data.pilot;
    const tipAttr = PFC.tipAttr;
    document.documentElement.lang = "ko";
    document.title = S.cover_title.ko + " — " + data.name;

    const label = (key, tag) => "<" + (tag || "span") + tipAttr(S[key].tip) + ">" + esc(S[key].ko) + "</" + (tag || "span") + ">";
    const pages = [];
    const page = (cls, html, part) => {
        pages.push('<section class="pf-page dprk ' + cls + '"' + (part ? ' data-part="' + part + '"' : "") + ">" + html + "</section>");
    };
    const field = (key, value, tip) => '<div class="pf-field"><span class="k"' + tipAttr(S[key].tip) + ">" + esc(S[key].ko) +
        '</span><span class="v"' + tipAttr(tip) + ">" + esc(value || " ") + "</span></div>";
    const td = (text, tip, cls) => "<td" + (cls ? ' class="' + cls + '"' : "") + tipAttr(tip) + ">" + esc(text) + "</td>";
    const photo = "/api/photo/" + enc(careerId) + "/" + enc(p.id) + "?avatar=" + enc(p.avatar || "") + "&h=512";

    // 1 - 간부리력서
    page("portrait cover",
        '<div class="dprk-head">' + label("cover_title", "h1") + "</div>" +
        '<div class="pf-cover"><div class="pf-fields">' +
            field("label_name", data.name, data.latin) +
            field("label_sex", "남", "") +
            field("label_born", data.birth_ko, data.born_tip) +
            field("label_home", data.born_place, data.bio_tip.born) +
            field("label_nation", "조선", "") +
            field("label_party", data.party, data.bio_tip.party) +
            field("label_enlisted", data.enlisted ? data.enlisted + "년" : "", data.bio_tip.since) +
            field("label_rank", data.rank, data.rank_tip) +
            field("label_post", data.post, data.post_tip) +
            field("label_unit", data.unit.full, data.unit_tip) +
        "</div>" +
        '<div class="pf-photo"><img alt="" src="' + photo + '" onerror="this.parentNode.style.visibility=\'hidden\'"></div></div>' +
        '<div class="pf-section pf-contents">' + label("contents", "h3") +
            '<table class="pf-table"><tbody id="pf-contents"></tbody></table></div>' +
        (["kia", "missing"].indexOf(p.state) >= 0
            ? '<img class="pf-stamp" src="/static/images/stamps/' + esc(p.state) + '.png" alt="">' : ""), "cover");

    // 2 - 복무경력
    const rows = (cols, body) => '<table class="pf-table"><thead><tr>' + cols.map((c) => "<th>" + label(c) + "</th>").join("") +
        "</tr></thead><tbody>" + body + "</tbody></table>";
    const st = data.stats || {};
    page("portrait flow",
        '<div class="dprk-head">' + label("record_title", "h2") + "</div>" +
        '<div class="pf-section">' + label("record_ranks", "h3") + rows(["col_date", "col_rank"],
            (data.promotions || []).map((r) => "<tr>" + td(r.date_ko, r.date, "date") + td(r.rank, r.rank_tip) + "</tr>").join("")) + "</div>" +
        '<div class="pf-section">' + label("record_battles", "h3") + "<p" + tipAttr(data.bio_tip.battles) + ">" +
            esc(data.battles) + "</p></div>" +
        '<div class="pf-section">' + label("record_awards", "h3") + rows(["col_date", "col_award"],
            (data.record || []).map((a) => "<tr>" + td(a.date_ko, a.date, "date") + td(a.name, a.name_tip) + "</tr>").join("")) + "</div>" +
        '<div class="pf-section">' + label("record_combat", "h3") + '<table class="pf-table"><tbody>' +
            [["stat_sorties", st.sorties], ["stat_hours", st.hours], ["stat_air", st.air], ["stat_ground", st.ground]]
                .map(([k, v]) => "<tr>" + td(S[k].ko, S[k].tip) + '<td class="num">' + esc(v == null ? "" : v) + "</td></tr>").join("") +
        "</tbody></table></div>", "record");

    // 3, 4 - booklets and the Hero's certificate
    (data.images || []).forEach((im) => {
        const portrait = im.size[0] < im.size[1];
        page(portrait ? "portrait" : "landscape",
            '<div class="pf-centre">' + PFC.doc(im, portrait ? 726 : 996, portrait ? 966 : 756, photo) + "</div>", im.part);
    });

    // 6 - nomination sheets
    (data.sheets || []).forEach((s) => page("portrait cert",
        '<div class="pf-centre"><div class="pf-fit" data-kind="cert"><iframe loading="eager" src="/certificate?embed=1&career=' +
        enc(careerId) + "&pilot=" + enc(p.id) + "&award=" + enc(s.type) + "&earned=" + enc(s.earned) +
        '" title=""></iframe></div></div>', "sheets"));

    // 7 - 자서전, in the reader's language: the game wrote none in Korean
    if ((data.biography || []).length) {
        const f = data.bio_fields || {};
        const fill = (s) => String(s || "").replace(/\$\[([^\]]+)\]/g, (whole, k) =>
            Object.prototype.hasOwnProperty.call(f, k) ? f[k] : whole);
        // Korean where a Korean version exists, each paragraph with the
        // reader's own beneath it; else the reader's, marked as a translation.
        const said = data.biography_tips || [];
        page("portrait flow pf-bio", '<div class="dprk-head">' + label("biography_title", "h2") +
            (data.biography_korean ? "" : '<div class="dprk-note">(' + label("translation") + ")</div>") + "</div>" +
            data.biography.map((s, i) => /^#+\s/.test(s)
                ? "<h4" + tipAttr(said[i]) + ">" + esc(fill(s.replace(/^#+\s*/, ""))) + "</h4>"
                : "<p" + tipAttr(said[i]) + ">" + esc(fill(s)) + "</p>").join(""), "biography");
    }

    // 8 - 훈장함
    let box = null;
    try {
        const r = await fetch("/api/shadowbox/" + enc(careerId) + "?pilot=" + enc(p.id));
        if (r.ok) box = await r.json();
    } catch (_e) { box = null; }
    if (box) page("landscape", '<div class="pf-centre"><div class="pf-sbox" id="pf-sbox"></div></div>', "shadowbox");

    el("pf-doc").innerHTML = pages.join("");
    if (box) PFC.shadowbox(el("pf-sbox"), box);
    PFC.tooltips();

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

    const order = [];
    document.querySelectorAll(".pf-page[data-part]").forEach((s) => {
        const part = s.dataset.part;
        if (part !== "cover" && order.indexOf(part) < 0) order.push(part);
    });
    el("pf-contents").innerHTML = order.map((x, i) => {
        const s = S["part_" + x] || {ko: x, tip: ""};
        return '<tr><td class="num">' + esc(i + 1) + ".</td><td" + tipAttr(s.tip) + ">" + esc(s.ko) + "</td></tr>";
    }).join("");
};
