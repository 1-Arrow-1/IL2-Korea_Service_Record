/*
 * What the three personnel files share (personnel.js for the USAF,
 * personnel_prc.js and personnel_ussr.js):
 *
 *   PFC.doc       a filled-in document picture with a hover region per field
 *   PFC.tooltips  the one tooltip box that follows the pointer (screen only)
 *   PFC.settle    an embedded page (certificate, flight record) laid out at
 *                 its own design width and scaled down into its box
 *   PFC.shadowbox the shadowbox drawn into a page
 */
window.PFC = (function () {
    "use strict";
    const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
        ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
    const tipAttr = (t) => (t ? ' data-tip="' + esc(t) + '"' : "");

    // im: {src, size: [W, H], regions: [[x, y, w, h, tip]...], photo?: [x, y, w, h]}
    // in template pixels; photoSrc fills im.photo when given.
    const doc = (im, maxW, maxH, photoSrc) => {
        const [W, H] = im.size;
        const k = Math.min(maxW / W, maxH / H);
        const pct = (r) => "left:" + (r[0] / W * 100) + "%;top:" + (r[1] / H * 100) + "%;width:" +
            (r[2] / W * 100) + "%;height:" + (r[3] / H * 100) + "%";
        return '<div class="prc-doc" style="width:' + Math.round(W * k) + "px;height:" + Math.round(H * k) + 'px">' +
            '<img src="' + esc(im.src) + '" alt="">' +
            (im.photo && photoSrc ? '<img class="doc-photo" style="' + pct(im.photo) + '" src="' + esc(photoSrc) +
                '" alt="" onerror="this.remove()">' : "") +
            (im.regions || []).filter((r) => r[4]).map((r) => '<span class="prc-region" style="' + pct(r) + '"' +
                tipAttr(r[4]) + "></span>").join("") + "</div>";
    };

    const tooltips = () => {
        const box = document.createElement("div");
        box.className = "prc-tip no-print";
        box.hidden = true;
        document.body.appendChild(box);
        document.addEventListener("mousemove", (ev) => {
            const target = ev.target.closest && ev.target.closest("[data-tip]");
            if (!target) { box.hidden = true; return; }
            box.textContent = target.dataset.tip;
            box.hidden = false;
            const pad = 14;
            let x = ev.clientX + pad, y = ev.clientY + pad;
            const r = box.getBoundingClientRect();
            if (x + r.width > window.innerWidth - 8) x = ev.clientX - r.width - pad;
            if (y + r.height > window.innerHeight - 8) y = ev.clientY - r.height - pad;
            box.style.left = x + "px";
            box.style.top = y + "px";
        });
    };

    const ready = (frame) => new Promise((resolve) => {
        const check = () => {
            const d = frame.contentDocument;
            if (d && d.body && d.body.dataset.ready === "1") {
                if (!Array.from(d.images).some((im) => !im.complete)) { resolve(d); return; }
            }
            setTimeout(check, 120);
        };
        check();
    });

    // A .pf-fit holding an iframe: laid out wide, measured, scaled into its
    // page's box. A certificate that cannot be drawn takes its page with it;
    // a landscape sheet turns its page landscape.
    const settle = async (fit) => {
        const frame = fit.querySelector("iframe");
        frame.style.width = "1200px";
        frame.style.height = "1600px";
        const d = await ready(frame);
        const sheet = d.querySelector(".sheet");
        const pageEl = fit.closest(".pf-page");
        if (!sheet || (d.getElementById("ct-state") && !d.getElementById("ct-state").hidden)) {
            if (fit.dataset.kind === "cert") pageEl.remove(); else fit.closest(".pf-half").remove();
            return;
        }
        const w = sheet.offsetWidth, h = sheet.offsetHeight;
        if (fit.dataset.kind === "cert" && w > h) {
            pageEl.classList.remove("portrait");
            pageEl.classList.add("landscape");
        }
        const landscape = pageEl.classList.contains("landscape");
        const boxW = fit.dataset.kind === "logbook" ? 726 : (landscape ? 996 : 726);
        const boxH = fit.dataset.kind === "logbook" ? 476 : (landscape ? 756 : 966);
        const k = Math.min(1, boxW / w, boxH / h);
        frame.style.width = w + "px";
        frame.style.height = h + "px";
        frame.style.transform = "scale(" + k + ")";
        fit.style.width = Math.round(w * k) + "px";
        fit.style.height = Math.round(h * k) + "px";
    };

    // The shadowbox (/api/shadowbox), laid out as on the career page.
    const shadowbox = (holder, box) => {
        const [W, H] = box.size || [2050, 1860];
        const k = Math.min(996 / W, 756 / H);
        holder.style.width = Math.round(W * k) + "px";
        holder.style.height = Math.round(H * k) + "px";
        const pos = (o) => "left:" + o.left + "%;top:" + o.top + "%;width:" + o.width + "%;height:" + o.height + "%";
        holder.innerHTML = '<img class="frame" src="' + esc(box.frame) + '" alt="">' +
            '<div class="items">' + (box.items || []).map((it) => '<img class="' + esc(it.cls || "") + '" src="' +
                esc(it.src) + '" alt="" style="' + pos(it) + '">').join("") + "</div>" +
            '<div class="pf-plate" style="' + pos(box.plate) + '"><span class="name"></span><span class="unit"></span></div>' +
            '<img class="glass" src="' + esc(box.glass.src) + '" alt="" style="' + pos(box.glass) + '">';
        // the engraving, fitted inside the plate's frame as on the career page
        const plate = holder.querySelector(".pf-plate");
        const text = box.text || {};
        Nameplate.fit(plate, plate.querySelector(".name"), plate.querySelector(".unit"),
                      [text.full, text.short], box.squadron || "");
    };

    return {esc: esc, tipAttr: tipAttr, doc: doc, tooltips: tooltips, settle: settle, shadowbox: shadowbox};
})();
