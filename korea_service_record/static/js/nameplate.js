/*
 * The shadowbox nameplate, fitted to the brass for every country: on the
 * career page, in the saved picture (which copies what the page drew) and
 * in the personnel files.
 *
 * The engraving stays inside the plate's inner frame and clear of its two
 * screws - the field is the middle 77% of the plate's width and 80% of its
 * height. The rank always arrives abbreviated (shadowbox.RANK_ABBR); the
 * name is engraved in full where it fits at a readable size, else with
 * its first name cut to an initial ("Lt. Col. A. Bleiholder"), and only
 * a name too long even for that ends in an ellipsis. The unit goes on a
 * second line, always smaller than rank and name; a long unit shrinks on
 * its own and never takes size from the name.
 */
window.Nameplate = (function () {
    "use strict";
    const FIELD_W = 0.77;
    const FIELD_H = 0.80;
    const UNIT = 0.72;          // the unit line against the name line

    const ellipsis = (line, value, room) => {
        line.textContent = value;
        if (line.scrollWidth <= room) { return; }
        let lo = 0, hi = value.length;
        while (lo < hi) {                         // longest prefix that fits
            const mid = Math.ceil((lo + hi) / 2);
            line.textContent = value.slice(0, mid).trimEnd() + "…";
            if (line.scrollWidth <= room) { lo = mid; } else { hi = mid - 1; }
        }
        line.textContent = value.slice(0, lo).trimEnd() + "…";
    };

    // holder: the plate box; nameLine and unitLine: its two text lines.
    // candidates: the engravings to try, best first (rank and full name,
    // then rank and initial).
    const fit = (holder, nameLine, unitLine, candidates, unit) => {
        const height = holder.clientHeight;
        if (!height || !nameLine) { return; }
        const room = holder.clientWidth * FIELD_W;
        const two = Boolean(unit);
        if (unitLine) {
            unitLine.textContent = unit || "";
            unitLine.hidden = !two;
        }
        // Two lines share the field with a breath between them; one line
        // may stand taller.
        const want = height * FIELD_H * (two ? 0.46 : 0.62);
        // smaller letters before a cut name: "Montgom…" says less than small type
        const least = want * 0.55;
        const gap = two ? height * 0.05 : 0;
        holder.style.rowGap = gap + "px";

        const widthAt = (line, text, size) => {
            line.textContent = text;
            line.style.fontSize = size + "px";
            return line.scrollWidth;
        };
        // 0.97: scrollWidth is whole pixels, and a size computed to the exact
        // width would sometimes miss by one and cut the last letter.
        const sizeFor = (text) => {
            const w = widthAt(nameLine, text, want);
            return w > room ? want * room / w * 0.97 : want;
        };
        // The full name where it stands at nearly the preferred size; if not,
        // the first name becomes an initial before the letters get smaller.
        const comfortable = want * 0.85;
        const options = candidates.filter(Boolean);
        let text = options[0] || "", size = sizeFor(text);
        for (const option of options) {
            const s = sizeFor(option);
            if (s >= comfortable) { text = option; size = s; break; }
            if (s > size) { text = option; size = s; }
        }
        size = Math.max(size, least);
        nameLine.style.fontSize = size + "px";
        ellipsis(nameLine, text, room);

        if (two && unitLine) {
            let unitSize = size * UNIT;
            const w = widthAt(unitLine, unit, unitSize);
            if (w > room) { unitSize = Math.max(unitSize * room / w, least * UNIT * 0.8); }
            unitLine.style.fontSize = unitSize + "px";
            ellipsis(unitLine, unit, room);
        }
        // Both lines together inside the frame's height.
        const total = nameLine.offsetHeight + (two && unitLine ? unitLine.offsetHeight + gap : 0);
        if (total > height * FIELD_H) {
            const k = height * FIELD_H / total;
            nameLine.style.fontSize = parseFloat(nameLine.style.fontSize) * k + "px";
            if (two && unitLine) { unitLine.style.fontSize = parseFloat(unitLine.style.fontSize) * k + "px"; }
        }
    };

    return {fit: fit};
})();
