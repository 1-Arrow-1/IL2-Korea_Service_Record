/* The player's selected in-game biography, measured into an unlimited set
 * of two-page booklet spreads. */
(async function () {
    "use strict";

    const el = (id) => document.getElementById(id);
    const params = new URLSearchParams(location.search);
    const careerId = params.get("career");
    const pilotId = params.get("pilot");

    const settings = await fetch("/api/settings").then((r) => r.json()).catch(() => ({}));
    const override = (settings.overrides || []).find((o) => o.career === careerId);
    const lang = (override && override.language) || settings.language || "en";
    await i18n.init(lang);
    i18n.apply(document.body);
    document.documentElement.lang = lang;
    const T = (key, values) => i18n.t("biography." + key, values);

    const back = el("bio-back");
    back.href = careerId ? "/#career/" + encodeURIComponent(careerId) : "/";
    back.addEventListener("click", (event) => {
        const parent = window.opener;
        if (!parent || parent.closed) { return; }
        event.preventDefault();
        const href = back.href;
        try {
            parent.location.href = href;
            parent.focus();
            window.close();
            setTimeout(() => {
                if (!window.closed) { window.location.href = href; }
            }, 100);
        } catch (_error) {
            window.location.href = href;
        }
    });

    const fail = (key) => {
        el("bio-state").textContent = T(key);
        el("bio-state").hidden = false;
        el("bio-book").hidden = true;
    };
    if (!careerId) { fail("not_found"); return; }

    let data;
    try {
        const suffix = pilotId ? "/" + encodeURIComponent(pilotId) : "";
        const response = await fetch("/api/biography/" + encodeURIComponent(careerId) + suffix);
        if (!response.ok) {
            fail(response.status === 404 ? "not_found" : "failed");
            return;
        }
        data = await response.json();
    } catch (_error) {
        fail("failed");
        return;
    }

    const longDate = (raw) => {
        const parts = String(raw || "").split(/[.\-/]/).map(Number);
        if (parts.length !== 3 || !parts[0]) { return raw || ""; }
        return new Intl.DateTimeFormat(lang, {
            day: "numeric", month: "long", year: "numeric"
        }).format(new Date(parts[0], parts[1] - 1, parts[2]));
    };
    const fields = {
        name: data.pilot.name,
        firstName: data.pilot.first_name,
        lastName: data.pilot.last_name,
        birthDate: longDate(data.pilot.birth_date),
        startRank: data.pilot.starting_rank,
    };
    const fill = (text) => String(text || "").replace(/\$\[([^\]]+)\]/g,
        (whole, key) => Object.prototype.hasOwnProperty.call(fields, key) ? fields[key] : whole);
    const source = data.paragraphs.map(fill);

    document.title = T("title") + " — " + data.pilot.name;
    el("bio-note").textContent = data.pilot.name;
    const book = el("bio-book");
    if (book.dataset.art) {
        book.style.backgroundImage = 'url("' + book.dataset.art + '")';
        book.classList.add("has-art");
    }

    const left = el("bio-left-content");
    const right = el("bio-right-content");
    const measure = el("bio-measure");
    const pager = el("bio-pager");
    const previous = el("bio-prev");
    const next = el("bio-next");
    let pages = [];
    let spread = 0;

    function heading() {
        const node = document.createElement("header");
        node.className = "bio-heading";
        const title = document.createElement("h1");
        title.textContent = T("title");
        const pilot = document.createElement("h2");
        pilot.textContent = data.pilot.name;
        node.append(title, pilot);
        return node;
    }

    function paragraph(entry) {
        const node = document.createElement("p");
        node.textContent = entry.text;
        if (entry.continued) { node.classList.add("continued"); }
        return node;
    }

    function renderPage(target, page) {
        target.replaceChildren();
        if (!page) { return; }
        if (page.heading) { target.append(heading()); }
        page.paragraphs.forEach((entry) => target.append(paragraph(entry)));
    }

    function overflows() {
        return measure.scrollHeight > measure.clientHeight + 1;
    }

    function paginate() {
        pages = [];
        let page = {heading: true, paragraphs: []};
        renderPage(measure, page);

        source.forEach((text) => {
            const words = text.split(/\s+/).filter(Boolean);
            let chunk = [];
            let continued = false;
            let node = paragraph({text: "", continued: false});
            measure.append(node);

            words.forEach((word) => {
                chunk.push(word);
                node.textContent = chunk.join(" ");
                if (!overflows()) { return; }

                chunk.pop();
                if (chunk.length) {
                    node.textContent = chunk.join(" ");
                    page.paragraphs.push({text: node.textContent, continued});
                } else {
                    node.remove();
                }
                pages.push(page);
                page = {heading: false, paragraphs: []};
                renderPage(measure, page);
                continued = chunk.length > 0;
                chunk = [word];
                node = paragraph({text: word, continued});
                measure.append(node);
            });

            if (chunk.length) {
                page.paragraphs.push({text: chunk.join(" "), continued});
            }
        });
        if (page.heading || page.paragraphs.length) { pages.push(page); }
        measure.replaceChildren();
    }

    function showSpread() {
        const spreads = Math.max(1, Math.ceil(pages.length / 2));
        spread = Math.max(0, Math.min(spread, spreads - 1));
        const from = spread * 2;
        renderPage(left, pages[from]);
        renderPage(right, pages[from + 1]);
        el("bio-pages").textContent = T("pages", {
            from: from + 1,
            to: Math.min(pages.length, from + 2),
            total: pages.length,
        });
        el("bio-page-left").textContent = from + 1;
        el("bio-page-right").textContent = pages[from + 1] ? from + 2 : "";
        previous.disabled = spread === 0;
        next.disabled = spread >= spreads - 1;
        pager.hidden = spreads <= 1;
        book.classList.remove("loading");
    }

    function layout() {
        if (!measure.clientHeight || !measure.clientWidth) { return; }
        paginate();
        showSpread();
    }

    previous.addEventListener("click", () => { spread -= 1; showSpread(); });
    next.addEventListener("click", () => { spread += 1; showSpread(); });
    let resizeTimer;
    window.addEventListener("resize", () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(layout, 120);
    });
    requestAnimationFrame(layout);
    if (document.fonts && document.fonts.ready) { document.fonts.ready.then(layout); }
})();
