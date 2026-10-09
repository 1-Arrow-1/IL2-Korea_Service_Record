/*
 * Short forms of the game's own rank names, in all six of its languages,
 * for places too narrow for "Lieutenant Colonel": the flight record's GRADE
 * box and the roster's promotion line. A name with no entry is short
 * enough already and comes back unchanged.
 */
(function () {
    "use strict";

    const SHORT_RANKS = {
        // English (the Spanish game names US and some Soviet ranks in English too)
        "Second Lieutenant": "2nd Lt.", "First Lieutenant": "1st Lt.", "Senior Lieutenant": "Sr. Lt.",
        "Lieutenant Colonel": "Lt. Colonel", "Lieutenant General": "Lt. General",
        "Brigadier General": "Brig. General", "Major General": "Maj. General",
        "Lieutenant Junior Grade": "Lt. (jg)", "Lieutenant Commander": "Lt. Commander",
        "Rear Admiral (LH)": "Rear Adm. (LH)", "Rear Admiral (UH)": "Rear Adm. (UH)",
        "Rear Admiral (lower half)": "Rear Adm. (LH)", "Rear Admiral": "Rear Adm.",
        // Spanish transliterations of Soviet ranks
        "Starshy Leytenant": "St. Leytenant", "General-leytenant": "Gen.-leyt.",
        "General-mayor": "Gen.-mayor", "Podpolkovnik": "Podpolk.",
        // German
        "Oberleutnant": "Oblt.", "Oberstleutnant": "Oberstlt.", "Generalmajor": "GenMaj.",
        "Generalleutnant": "GenLt.", "Brigadegeneral": "BrigGen.",
        "Leutnant zur See": "Lt. z. S.", "Oberleutnant zur See": "Oblt. z. S.",
        "Kapitänleutnant": "KptLt.", "Korvettenkapitän": "KKpt.", "Fregattenkapitän": "FKpt.",
        "Kapitän zur See": "Kpt. z. S.", "Flottillenadmiral": "FltlAdm.", "Konteradmiral": "KAdm.",
        // French
        "Sous-lieutenant": "S/Lt", "Lieutenant senior": "Lt senior", "Lieutenant-colonel": "Lt-colonel",
        "Général-major": "Gal-major", "Général-lieutenant": "Gal-lt",
        "Général de brigade": "Gal de brig.", "Général de division": "Gal de div.",
        "Lieutenant de vaisseau junior": "Lt de vaiss. jr", "Lieutenant de vaisseau": "Lt de vaiss.",
        "Capitaine de corvette": "Cne de corv.", "Capitaine de frégate": "Cne de frég.",
        "Capitaine de vaisseau": "Cne de vaiss.", "Contre-amiral": "C.-amiral",
        // Russian
        "Второй лейтенант": "2-й лейтенант", "Первый лейтенант": "1-й лейтенант",
        "Старший лейтенант": "Ст. лейтенант", "Младший лейтенант": "Мл. лейтенант",
        "Подполковник": "Подполк.", "Генерал-майор": "Ген.-майор", "Генерал-лейтенант": "Ген.-лейт.",
        "Бригадный генерал": "Бриг. генерал", "Лейтенант-коммандер": "Лейт.-комм.",
        "Контр-адмирал": "Контр-адм.",
    };

    window.shortRank = (name) => {
        const full = String(name == null ? "" : name).trim();
        return SHORT_RANKS[full] || full;
    };
})();
