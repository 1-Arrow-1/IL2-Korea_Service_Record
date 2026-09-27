/*
 * The squadron's war diary.
 *
 * The server hands over facts, never sentences: each line arrives as
 * {key, count, who, name, ...} and the sentence is built here out of the
 * locale file. That is the only way six languages can be right - the
 * server does not know that German puts the verb last or that Russian
 * declines a name after a preposition, and it should not have to.
 *
 * Strings: diary.* in the locale files.
 */
(async function () {
    "use strict";

    const el = (id) => document.getElementById(id);
    const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
        ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
    const params = new URLSearchParams(location.search);
    const careerId = params.get("career");

    const settings = await fetch("/api/settings").then((r) => r.json()).catch(() => ({}));
    const override = (settings.overrides || []).find((o) => o.career === careerId);
    const lang = (override && override.language) || settings.language || "en";
    await i18n.init(lang);
    i18n.apply(document.body);
    document.documentElement.lang = lang;
    el("wd-back").href = careerId ? "/#career/" + encodeURIComponent(careerId) : "/";
    el("wd-print").addEventListener("click", () => window.print());

    // The letterhead's engraving reaches in from both ends and leaves the
    // middle 41% clear. CSS caps the title at that span; this shrinks the
    // type until it actually fits inside it, because the word is nine
    // characters in English and twenty-two in Russian.
    function fitTitle() {
        const h1 = el("wd-title");
        if (!h1 || !h1.offsetWidth) { return; }
        let size = 1.5;
        h1.style.fontSize = size + "rem";
        // scrollWidth exceeds clientWidth exactly while the text overflows
        // the capped box; 0.55rem is small but still legible on a phone.
        while (h1.scrollWidth > h1.clientWidth + 1 && size > 0.55) {
            size -= 0.04;
            h1.style.fontSize = size.toFixed(2) + "rem";
        }
    }

    const fail = (key) => {
        el("wd-state").textContent = i18n.t(key);
        el("wd-state").hidden = false;
        el("wd-sheet").hidden = true;
    };
    if (!careerId) { fail("diary.no_career"); return; }

    let data;
    try {
        const r = await fetch("/api/diary/" + encodeURIComponent(careerId));
        if (!r.ok) throw new Error(r.status);
        data = await r.json();
    } catch (err) { fail("diary.failed"); return; }

    // "2 April 1951" in the reader's own language and order. The career
    // date is "1951.04.02"; built with explicit numbers rather than
    // Date.parse so no timezone can move it a day.
    const LONG = new Intl.DateTimeFormat(lang, {day: "numeric", month: "long", year: "numeric"});
    function longDate(ymd) {
        const [y, m, d] = ymd.split(".").map(Number);
        if (!y) { return ymd; }
        return LONG.format(new Date(y, m - 1, d));
    }
    const T = (key, p) => i18n.t("diary." + key, p);
    const num = (n) => Number(n).toLocaleString(lang);

    // Fifteen replacements can report on one morning, and fifteen names
    // in a row stop being a sentence. Six and a count, which still names
    // most of a normal intake; the server keeps the whole list either way.
    const NAME_CAP = 6;
    function nameList(names) {
        if (names.length <= NAME_CAP) { return names.join(", "); }
        const rest = names.length - NAME_CAP;
        return names.slice(0, NAME_CAP).join(", ") + " " + T("and_others", {n: rest});
    }

    // One note, as a sentence. The key the server sent decides which
    // sentence; everything else it sent is a placeholder in it.
    function noteText(n) {
        const key = n.key.replace(/^diary\./, "");
        // `n` goes through as a number: it both fills {n} and picks the
        // plural form, and Intl.PluralRules cannot select on "1,551".
        const parts = {
            who: n.who || "", n: n.count == null ? 0 : n.count,
            name: n.name || "", what: n.what || "", field: n.field || "",
            award: n.award || "", value: n.value == null ? "" : num(n.value),
            health: n.health == null ? "" : num(n.health),
            names: nameList(n.names || []),
        };
        const text = T(key, parts);
        // A key the locale has not caught up with returns itself; the
        // server's English is the fallback rather than "diary.wounded".
        return text === "diary." + key ? (n.label || "") : text;
    }

    // The ribbon itself, in front of his own decorations. The only colour
    // on the sheet, so the reader's own thread is findable at a glance.
    const artArg = () => (data.art_rev ? "?r=" + encodeURIComponent(data.art_rev) : "");
    function ribbon(n) {
        if (!n.award_id) { return ""; }
        // A badge has no ribbon - it is worn above them - so it shows as
        // the atlas icon instead. The server says which is which, rather
        // than the page finding out by asking for a 404.
        const src = n.ribbon
            ? "/api/ribbon/" + encodeURIComponent(n.award_id) + artArg() +
              (data.navy ? (artArg() ? "&" : "?") + "svc=navy" : "")
            : "/api/icon/award/" + encodeURIComponent(n.award_id) + "?h=48" +
              (data.art_rev ? "&r=" + encodeURIComponent(data.art_rev) : "");
        return '<img class="wd-ribbon' + (n.ribbon ? "" : " badge") + '" alt="" src="' +
            src + '" onerror="this.style.display=&quot;none&quot;">';
    }

    // The stamp struck against a casualty, from the same set the roster
    // uses. A period document said this with a rubber stamp, not a word.
    const STAMPS = {pilot_kia: "kia", pilot_missing: "missing", wounded: "wounded"};
    function stamp(key) {
        const name = STAMPS[key];
        return name ? '<img class="wd-stamp" alt="" src="/static/images/stamps/' +
            name + '.png">' : "";
    }

    function noteClass(n) {
        const key = n.key.replace(/^diary\./, "");
        if (["pilot_kia", "pilot_missing", "wounded", "plane_lost",
             "friendly_destroyed", "resources_destroyed"].includes(key)) { return "loss"; }
        if (["own_granted", "own_presented", "own_both"].includes(key)) { return "mine"; }
        if (["operation_begin", "operation_end", "transfer_ordered", "transfer_done"].includes(key)) { return "op"; }
        return "";
    }

    function missionLine(m) {
        const head = m.num ? T("mission_num", {n: num(m.num)}) : T("unscheduled");
        const bits = [];
        // The place, with no preposition in front of it. "against Sinnam"
        // was right for an attack and wrong for everything else - an
        // airfield defence is not flown against the field it protects, nor
        // an escort against the place it passes. The mission types run from
        // interception to cargo delivery to a squadron transfer, and no one
        // preposition fits them all in English, let alone in six languages.
        // A log entry does not need one.
        if (m.place) { bits.push(m.place); }
        if (m.targets) { bits.push(T("targets", {n: m.targets})); }
        return '<li class="wd-mission' + (m.player ? " flown" : "") + '">' +
            '<span class="wd-m-head">' + esc(head) + "</span>" +
            '<span class="wd-m-type">' + esc(m.type || "") + "</span>" +
            (bits.length ? '<span class="wd-m-rest">' + esc(bits.join(" · ")) + "</span>" : "") +
            (m.player ? '<span class="wd-flown" title="' + esc(T("you_flew")) + '">★</span>' : "") +
            "</li>";
    }

    // An operation beginning or ending divides the diary into chapters.
    // Pulled out of the day's lines and set as a band across the sheet,
    // because it is the only thing in the file that changes what the
    // squadron is for.
    function bandsOf(day) {
        return day.notes.filter((n) => /operation_(begin|end)$/.test(n.key));
    }
    function band(n) {
        const ending = /operation_end$/.test(n.key);
        return '<li class="wd-band' + (ending ? " ending" : "") + '">' +
            '<span>' + esc(noteText(n)) + "</span></li>";
    }

    function dayBlock(day) {
        const tallies = [];
        if (day.granted) { tallies.push(T("granted", {n: day.granted})); }
        if (day.presented) { tallies.push(T("presented", {n: day.presented})); }
        if (day.targets) { tallies.push(T("targets", {n: day.targets})); }
        const bands = bandsOf(day);
        day = Object.assign({}, day, {notes: day.notes.filter((n) => !bands.includes(n))});
        const quiet = !day.missions.length && day.notes.length <= 1 && !tallies.length;
        return bands.map(band).join("") +
            '<li class="wd-day' + (quiet ? " quiet" : "") + '">' +
            '<h2 class="wd-date">' + esc(longDate(day.date)) + "</h2>" +
            (day.missions.length
                ? '<ul class="wd-missions">' + day.missions.map(missionLine).join("") + "</ul>" : "") +
            (day.notes.length
                ? '<ul class="wd-notes">' + day.notes.map((n) => {
                    const key = n.key.replace(/^diary\./, "");
                    return '<li class="' + noteClass(n) + '">' + ribbon(n) +
                        esc(noteText(n)) + stamp(key) + "</li>";
                }).join("") + "</ul>" : "") +
            (tallies.length
                ? '<p class="wd-tally">' + esc(tallies.join(" · ")) + "</p>" : "") +
            "</li>";
    }

    document.title = T("title") + " — " + (data.squadron || "");
    el("wd-sub").textContent = [data.squadron, data.pilot].filter(Boolean).join(" · ");
    // The squadron's own emblem beside the title, its service's seal
    // blind-struck in the corner, and the aeroplane it flies along the
    // foot of the header. All three are art the tracker already holds.
    if (data.squadron_key) {
        el("wd-emblem").src = "/api/icon/squadron/" +
            encodeURIComponent(data.squadron_key) + "?h=128" +
            (data.art_rev ? "&r=" + encodeURIComponent(data.art_rev) : "");
        el("wd-emblem").hidden = false;
    }
    if (data.seal) {
        el("wd-seal").src = "/static/images/stamps/seal_" + data.seal + ".png";
        el("wd-seal").hidden = false;
    }
    if (data.plane) {
        el("wd-plane").src = "/static/images/planes/" + data.plane + ".png";
        el("wd-plane").hidden = false;
    }
    fitTitle();
    addEventListener("resize", fitTitle);
    if (!data.days.length) { fail("diary.empty"); return; }
    el("wd-note").textContent = T("days", {n: data.days.length});
    el("wd-days").innerHTML = data.days.map(dayBlock).join("");
})();
