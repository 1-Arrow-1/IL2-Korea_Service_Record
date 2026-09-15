/**
 * UI strings for the Korea Service Record.
 *
 * Same shape as the Great Battles tracker's helper so translation work carries
 * between the two projects: nested JSON, dot-notation keys, {param} holes.
 *
 * English is always loaded alongside the chosen language and used key by key
 * when something is missing, so a half-finished translation degrades one
 * string at a time instead of blanking a panel.
 *
 * Two languages can be in play at once. The chrome follows the global setting;
 * a career whose detail page is overridden renders in its own language. That
 * is why setLocale() is cheap to call repeatedly and why apply() takes a root
 * element rather than always walking the whole document.
 */
const i18n = {
    locale: "en",
    fallback: "en",
    loaded: {},
    ready: false,

    async load(code) {
        if (this.loaded[code]) return this.loaded[code];
        try {
            const response = await fetch("/locales/" + encodeURIComponent(code) + ".json");
            if (!response.ok) {
                console.warn("[i18n] no strings for " + code + " (" + response.status + ")");
                return null;
            }
            this.loaded[code] = await response.json();
            return this.loaded[code];
        } catch (err) {
            console.warn("[i18n] could not load " + code + ":", err);
            return null;
        }
    },

    async init(code) {
        await this.load(this.fallback);
        this.ready = true;
        await this.setLocale(code || this.fallback);
    },

    async setLocale(code) {
        const wanted = code || this.fallback;
        if (wanted !== this.fallback && !(await this.load(wanted))) {
            this.locale = this.fallback;
        } else {
            this.locale = wanted;
        }
        // The document's language, not just its strings: it picks the CJK
        // font for Chinese, tells a screen reader how to pronounce the page,
        // and is what hyphenation and quotation marks key on. index.html
        // hard-codes "en" and this is the only place it is ever corrected.
        document.documentElement.lang = this.locale;
        return this.locale;
    },

    _lookup(bundle, key) {
        let node = bundle;
        for (const part of key.split(".")) {
            if (!node || typeof node !== "object" || !(part in node)) return null;
            node = node[part];
        }
        return typeof node === "string" ? node : null;
    },

    /**
     * Translate one key. Unknown keys return the key itself rather than an
     * empty string — a visible "roster.status" in the UI is a bug report;
     * a blank cell is a mystery.
     */
    /** Whether a key exists in the current locale or the fallback. */
    has(key) {
        return this._lookup(this.loaded[this.locale], key) !== null
            || this._lookup(this.loaded[this.fallback], key) !== null;
    },

    t(key, params) {
        let text = this._lookup(this.loaded[this.locale], key);
        if (text === null) text = this._lookup(this.loaded[this.fallback], key);
        if (text === null) return key;
        if (params) {
            text = text.replace(/\{(\w+)\}/g, (match, name) =>
                (name in params ? String(params[name]) : match));
        }
        return text;
    },

    /**
     * Fill in every element carrying data-i18n beneath `root`.
     *
     * data-i18n           sets the text content
     * data-i18n-title     sets the title attribute
     * data-i18n-html      allows entities such as the back arrow
     */
    apply(root) {
        const scope = root || document;
        scope.querySelectorAll("[data-i18n]").forEach((el) => {
            el.textContent = this.t(el.dataset.i18n);
        });
        scope.querySelectorAll("[data-i18n-html]").forEach((el) => {
            el.innerHTML = this.t(el.dataset.i18nHtml);
        });
        scope.querySelectorAll("[data-i18n-title]").forEach((el) => {
            el.title = this.t(el.dataset.i18nTitle);
        });
    },
};
