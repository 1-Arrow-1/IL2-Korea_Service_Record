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

    function noteClass(n) {
        const key = n.key.replace(/^diary\./, "");
        if (["pilot_kia", "pilot_missing", "wounded", "plane_lost",
             "friendly_destroyed", "resources_destroyed"].includes(key)) { return "loss"; }
        if (["own_granted", "own_presented"].includes(key)) { return "mine"; }
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

    function dayBlock(day) {
        const tallies = [];
        if (day.granted) { tallies.push(T("granted", {n: day.granted})); }
        if (day.presented) { tallies.push(T("presented", {n: day.presented})); }
        if (day.targets) { tallies.push(T("targets", {n: day.targets})); }
        const quiet = !day.missions.length && day.notes.length <= 1 && !tallies.length;
        return '<li class="wd-day' + (quiet ? " quiet" : "") + '">' +
            '<h2 class="wd-date">' + esc(longDate(day.date)) + "</h2>" +
            (day.missions.length
                ? '<ul class="wd-missions">' + day.missions.map(missionLine).join("") + "</ul>" : "") +
            (day.notes.length
                ? '<ul class="wd-notes">' + day.notes.map((n) =>
                    '<li class="' + noteClass(n) + '">' + esc(noteText(n)) + "</li>").join("") + "</ul>" : "") +
            (tallies.length
                ? '<p class="wd-tally">' + esc(tallies.join(" · ")) + "</p>" : "") +
            "</li>";
    }

    document.title = T("title") + " — " + (data.squadron || "");
    el("wd-sub").textContent = [data.squadron, data.pilot].filter(Boolean).join(" · ");
    if (!data.days.length) { fail("diary.empty"); return; }
    el("wd-note").textContent = T("days", {n: data.days.length});
    el("wd-days").innerHTML = data.days.map(dayBlock).join("");
})();
