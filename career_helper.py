"""
IL-2 Korea Career Helper - two small mercies for a career, with a backup first.

    python career_helper.py

The Service Record never writes to a career. This tool does, on purpose and
narrowly, and it is kept apart from the tracker for that reason:

  * Revive a fallen AI pilot. Only while the career is still on the day he
    was lost - once the date has rolled, the game has moved on and so must
    you. The pilot returns to the line-up as "bailed out" (his aircraft stays
    written off, the loss stays in the squadron's history) or, if you tick
    the box, with his aircraft as well ("never happened"). The player's own
    character is never offered: the game already handles that with a
    successor, and unpicking it is another matter.

  * Add award points to the squadron. The game hands them out sparingly and
    the mod added many decorations that cost them; this tops the pool up.

  * Re-time the missions the player warped through (see corrections.py):
    compute the corrections - the tracker's own record, nothing in the game
    - and, if wanted, write the credited hours into the career for the pilot
    screen and the hours-based awards, or take them back again.

Every write is preceded by a copy of the career file into
%LOCALAPPDATA%\\IL2KoreaTracker\\backups\\ (never into the game's Career
folder - a second .db there would appear in the game as another career).
Close the game first; SQLite will refuse the write while the game holds the
file, and the tool says so rather than guessing.

What a death writes, and what revival undoes, is documented in the tracker's
notes: pilot.state 2/3, health 0, slot 5000+; sortie.status 2/3; plane.state 3;
event types 2 (aircraft lost) and 3 (killed) / 4 (missing).
"""

from __future__ import annotations

import io
import locale
import sqlite3
import urllib.parse
from datetime import datetime, timedelta
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict, List, NamedTuple, Optional

from PIL import Image, ImageTk

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from korea_service_record.locate import find_game_dir          # noqa: E402
from korea_service_record.settings import Settings             # noqa: E402
from korea_service_record.assets import default_cache_dir      # noqa: E402
from korea_service_record import corrections                   # noqa: E402
from korea_service_record.assets import AssetResolver           # noqa: E402
from korea_service_record.gamedata import loads_lenient         # noqa: E402
import custom_pilot_photo as pilot_photo                         # noqa: E402
from korea_service_record import custombio, wwii_awards          # noqa: E402
from korea_service_record.portraitfix import is_custom           # noqa: E402

BACKUPS = default_cache_dir().parent / "backups"
# The squadron's seats. 24 of them, which is what Career.SEATS has always
# used for the seating chart and what the game actually fills: this career
# has men in slots 20 to 23 right now. This constant said 20, so the four
# highest seats were invisible to everything that used it - a revived pilot
# was sent to the reserve pool with seats free, and a man whose place was
# 22 could not keep it.
#
# It is right for the American establishment and too small for the eastern
# one. scg/2/squadrons.cfg declares exactly two: 40 pilots / 24 aircraft
# (185 units, US pattern) and 48 / 48 (190 units, Soviet, Chinese and
# North Korean). A 48-seat regiment cannot be fully seated here yet.
LINEUP = range(0, 24)          # squadron line-up slots
RESERVE_BASE = 2000            # the replacement pool, when the line-up is full
STATE_NAMES = {2: "kia", 3: "mia"}

# ---------------------------------------------------------------------------
# Strings, six languages, keyed like the tracker's locales
# ---------------------------------------------------------------------------

STRINGS: Dict[str, Dict[str, str]] = {
    "en": {
        'tab_captured': 'Captured',
        'captured_intro': 'A pilot who bailed out or crash-landed over enemy ground: the game lets him walk back to the squadron in a couple of days. Mark him captured instead - the game then treats it like a loss (for the player: "Commander Captured", with a new commander to assign). Only a pilot\'s latest sortie counts.',
        'col_sortie': 'Sortie',
        'col_fate': 'Fate',
        'col_can2': 'Possible',
        'fate_evading': 'evading, back on {date}',
        'fate_lost_plane': 'aircraft lost, pilot back',
        'no_later': 'no - he has flown since',
        'no_candidates': 'Nobody went down over enemy ground in this career.',
        'capture': 'Mark as captured',
        'capture_confirm': 'Mark {name} as captured on {date}? The game will list him as missing in action.',
        'captured_done': '{name} is now missing in action - captured. Backup: {backup}',
        "title": "IL-2 Korea Career Helper",
        "subtitle": "Squadron paperwork for IL-2 Sturmovik: Korea",
        "career": "Career",
        "no_game": "No IL-2 Korea installation found.",
        "no_careers": "No careers found.",
        "tab_revive": "Revive a pilot",
        "tab_points": "Award points",
        "tab_flights": "Flights",
        "fl_intro": "Who sits where. A flight is four aircraft, a section two. Whoever holds the lowest-numbered seat you send commands the whole mission, and his three boosters cover every pilot in it - nobody else's count. Since any flight or section may be the one you send, the lead seats are the ones that carry boosters. Click a pilot, then click another, to swap them; each man's aircraft goes with him.",
        "fl_c1": "1 · Red",
        "fl_c2": "2 · Blue",
        "fl_c3": "3 · Green",
        "fl_c4": "4 · Yellow",
        "fl_c5": "5 · White",
        "fl_c6": "6 · Black",
        "fl_num": "Flight {n}",
        "fl_commander": "Commander Flight",
        # Only ever used past the third, where the game supplies no name:
        # "Squadron 4" rather than an ordinal we would have to inflect.
        "fl_squadron": "Squadron {n}",
        "fl_alert": "alert",
        "fl_empty": "— empty —",
        "fl_propose": "Propose a seating",
        "fl_apply": "Apply",
        "fl_reset": "Start over",
        "fl_hint": "Click a pilot, then another, to swap them.",
        "fl_cmd": "★ flight lead. Whichever flight or section you send, its senior seat takes command, so leads are chosen on their boosters.",
        "fl_you": "you",
        "fl_applied": "{n} pilots reseated. Backup: {backup}",
        "fl_nochange": "Nobody has moved, so there is nothing to apply.",
        "fl_ai": "AI",
        "fl_hurt": "hurt",
        "fl_b_boost": "Boosters",
        "fl_b_stats": "S/D/C",
        "fl_use_pool": "let the proposal draw on the reserve",
        "fl_bench_hint": "Pick a man here, then click a seat: he takes it and its aircraft, and the man he replaces goes down to the pool. One for one.",
        "fl_bench": "Reserve pool",
        "fl_none": "This career has no line-up to show.",
        "fl_moved": "{n} moved",
        "tab_photo": "Custom pilot photo",
        "photo_intro": "Choose a JPG or PNG. The helper removes the background locally, places you on the game's portrait background and creates the DDS used by this career. Close IL-2 Korea before applying or restoring.",
        "photo_current": "Current portrait: {path}",
        "photo_none": "No photo selected",
        "photo_choose": "Choose photo…",
        "photo_remove": "Remove background automatically",
        "photo_working": "Removing the background…",
        "photo_ready": "Drag the portrait to position it, then adjust zoom and edge cleanup.",
        "photo_drag": "Drag the preview to position the portrait.",
        "photo_zoom": "Zoom",
        "photo_edge": "Edge cleanup",
        "photo_exposure": "Exposure",
        "photo_contrast": "Contrast",
        "photo_saturation": "Saturation",
        "photo_sepia": "Sepia filter",
        "photo_sepia_strength": "Sepia strength",
        "photo_adjust_reset": "Reset adjustments",
        "photo_reset": "Reset position",
        "photo_apply": "Apply to this career",
        "photo_restore": "Restore original photo",
        "photo_applied": "Custom photo applied to {name}. DDS: {path}. Backup: {backup}",
        "photo_restored": "Original photo restored for {name}. Backup: {backup}",
        "photo_no_restore": "There is no original-photo record for this career.",
        "photo_filetypes": "Image files",
        "tab_bio": "Biography",
        "bio_intro": "The game shows your pilot's biography only when a career is created. Here you can rewrite it; the biography in the Service Record then shows your version. Text and medals change nothing in the game or in the career file, so the game may stay open.",
        "bio_vars": "Placeholders, filled in when the biography is shown - write them exactly like this: $[name] full name · $[firstName] first name · $[lastName] last name · $[birthDate] date of birth · $[startRank] rank at the start of the career. Leave an empty line between paragraphs.",
        "bio_source_game": "This is the game's biography. Change it and save to make it your own.",
        "bio_source_own": "This is your own biography, saved {date}.",
        "bio_count": "{n} of {max} characters",
        "bio_medals": "World War II medals",
        "bio_medals_nation": "Chinese and North Korean pilots have no World War II medals to choose.",
        "bio_medal_none": "not awarded",
        "bio_medal_plain": "medal",
        "bio_stars_hint": "★ = bronze service star, one per campaign",
        "bio_save": "Save biography",
        "bio_restore": "Restore the game's biography",
        "bio_saved": "Biography and medals saved for {name}. Reopen the biography in the Service Record to read it.",
        "bio_restored": "{name} has the game's biography and medals again.",
        "bio_unknown": "These placeholders are not known and will appear exactly as written:\n{vars}\n\nSave anyway?",
        "bio_too_long": "The biography is {n} characters long; the limit is {max}.",
        "bio_none": "This career has no biography to start from.",
        "bio_boost": "Boosters",
        "bio_boost_intro": "Your pilot has {total} booster points: {bio} from his biography and {promo} from promotions. Share them out again as you like, at most {max} on one attribute. Applying writes to the career: close IL-2 Korea first. A backup is taken.",
        "bio_boost_left": "{n} of {total} points still to share",
        "bio_boost_done": "All {total} points shared",
        "bio_boost_apply": "Apply boosters",
        "bio_boost_applied": "Boosters for {name} are now {values}. Backup: {backup}",
        "bio_boost_unknown": "The game data does not say how many points this biography gave, so its boosters cannot be shared out again.",
        "fl_legend": "The three numbers are the pilot's own skills / discipline / courage, as his panel shows them. ↑ is his boosters. AI is how the generated mission rates him in the air: his skill, but capped at 4 - so a pilot at 5 flies no better than one at 4, and a wound costs him a level.",
        "col_name": "Pilot", "col_state": "Fate", "col_date": "Lost on", "col_can": "Revivable",
        "kia": "killed in action", "mia": "missing in action",
        "yes": "yes", "no": "no - the career has moved on",
        "no_dead": "Nobody has been lost in this career.",
        "restore_plane": "Restore his aircraft too (otherwise: bailed out, aircraft lost)",
        "revive": "Revive",
        "revive_confirm": "Bring {name} back into the line-up?",
        "revived": "{name} is back in the line-up. Backup: {backup}",
        "rule": "A pilot can be revived on the day he was lost or the day after, your own as well as your squadron mates. Today is {date}.",
        "points_now": "The squadron's award points now: {points}",
        "points_add": "Add",
        "points_added": "Award points are now {points}. Backup: {backup}",
        "pending_intro": "Awards your pilots have earned but not yet been given. Each costs one award point. Click a line to include or exclude it, then hand them over.",
        "pend_col_who": "Pilot",
        "pend_col_award": "Award",
        "pend_col_earned": "Earned",
        "pend_col_sk": "Skill",
        "pend_col_di": "Discipline",
        "pend_col_co": "Courage",
        "pend_col_after": "after",
        "pend_all": "All",
        "pend_none": "None",
        "pend_grant": "Present the ticked awards",
        "pend_cost": "{n} ticked, {cost} points of {points}",
        "pend_short": "That needs {need} award points and the squadron has {points}. Add some first.",
        "pend_done": "{n} awards presented, {spent} points spent. Backup: {backup}",
        "pend_col_status": "Status",
        "st_active": "active",
        "st_reserve": "reserve",
        "st_notready": "not ready",
        "st_wounded": "wounded",
        "st_mia": "MIA",
        "st_kia": "KIA",
        "fl_unavailable": "{who} is not available - {state}. Only a pilot fit for duty can be brought up.",
        "st_returning": "on his way back",
        "locked": "The career file is in use - close IL-2 Korea and try again.",
        "failed": "That did not work: {error}",
        "player_note": "The player's own character is not listed: the game carries the career on with a successor, and this tool leaves that alone.",
        "refresh": "Refresh",
        "tab_times": "Flight time",
        "times_intro": "Missions whose flight log shows a jump to the target - part of the route skipped - re-timed to the plan, as the game does for missions flown without you. A sortie you simply ended early, with no jump in its log, is left alone. Computing only writes the tracker's own record; 'Apply' writes the credited hours into the career for the pilot screen and the hours-based awards, and 'Restore' takes them back.",
        "col_mission": "Mission",
        "col_flown": "Flown",
        "col_planned": "Planned",
        "col_source": "Timing from",
        "col_applied": "In the career",
        "src_log": "flight log",
        "src_plan": "plan only",
        "applied": "applied",
        "not_applied": "—",
        "compute": "Compute",
        "computed": "{n} missions re-timed; the tracker shows them with the switch on.",
        "apply": "Apply credited hours",
        "restore": "Restore game hours",
        "apply_confirm": "Write the corrected times of {n} mission(s) into the career and keep it corrected from now on? A backup is taken first.",
        "restore_confirm": "Put the game's own times back for all {n} corrected mission(s) and stop correcting this career? A backup is taken first.",
        "restore_awards": "{m} award(s) were earned on the added hours alone and will be withdrawn with them:",
        "restore_awards_done": "{m} award(s) withdrawn.",
        "applied_done": "Credited hours applied to {n} missions. Backup: {backup}",
        "restored_done": "Game hours restored for {n} missions. Backup: {backup}",
        "no_times": "No warped missions found - either you fly the whole route, or nothing has been flown yet.",
        "awards_since": "Awards granted since the hours were applied - tick the ones to withdraw (an award earned on kills should stay):",
        "withdraw": "Withdraw ticked awards",
        "auto_on": "This career is kept corrected: every mission flown from now on is re-timed when the Service Record next reads the career (backup first; skipped while the game holds the file). Restore puts all originals back and ends this.",
        "auto_off": "This career is not corrected. Apply writes the corrected times of every computed mission and keeps the career corrected from then on.",
        "open_from_tracker": "Please open the Career Helper from the Service Record - the button in its header.",
        "needs_mod": "The Career Helper is part of the awards mod. Install the mod component of the Service Record setup and enable modifications in IL-2 Korea.",
        "withdrawn": "{n} awards withdrawn. Backup: {backup}",
        "the_squadron": "The squadron",
    },
    "de": {
        'tab_captured': 'Gefangen',
        'captured_intro': 'Ein Pilot, der über Feindgebiet abgesprungen oder notgelandet ist: das Spiel lässt ihn in ein paar Tagen zur Staffel zurückkehren. Stattdessen als gefangen markieren - das Spiel behandelt es dann wie einen Verlust (beim Spieler: „Kommandeur gefangen“, ein neuer Kommandeur ist zu ernennen). Nur der letzte Einsatz eines Piloten zählt.',
        'col_sortie': 'Einsatz',
        'col_fate': 'Verbleib',
        'col_can2': 'Möglich',
        'fate_evading': 'auf dem Rückweg, zurück am {date}',
        'fate_lost_plane': 'Flugzeug verloren, Pilot zurück',
        'no_later': 'nein - er ist seitdem geflogen',
        'no_candidates': 'In dieser Laufbahn ist niemand über Feindgebiet abgestürzt.',
        'capture': 'Als gefangen markieren',
        'capture_confirm': '{name} am {date} als gefangen markieren? Das Spiel führt ihn dann als vermisst.',
        'captured_done': '{name} gilt jetzt als vermisst - in Gefangenschaft. Sicherung: {backup}',
        "title": "IL-2 Korea Laufbahn-Helfer",
        "subtitle": "Schreibstube der Staffel für IL-2 Sturmovik: Korea",
        "career": "Laufbahn",
        "no_game": "Keine IL-2-Korea-Installation gefunden.",
        "no_careers": "Keine Laufbahnen gefunden.",
        "tab_revive": "Piloten zurückholen",
        "tab_points": "Auszeichnungspunkte",
        "tab_flights": "Schwärme",
        "fl_intro": "Wer wo sitzt. Ein Schwarm sind vier Maschinen, eine Rotte zwei. Wer den niedrigsten eingesetzten Platz innehat, führt den gesamten Einsatz, und seine drei Boni gelten für jeden Piloten darin – die aller anderen zählen nicht. Da jeder Schwarm und jede Rotte der eingesetzte sein kann, sind es die Führungsplätze, auf die es bei den Boni ankommt. Einen Piloten anklicken, dann einen zweiten, um sie zu tauschen; die Maschine fliegt mit ihrem Piloten mit.",
        "fl_c1": "1 · Rot",
        "fl_c2": "2 · Blau",
        "fl_c3": "3 · Grün",
        "fl_c4": "4 · Gelb",
        "fl_c5": "5 · Weiß",
        "fl_c6": "6 · Schwarz",
        "fl_num": "Kette {n}",
        "fl_commander": "Stabsschwarm",
        "fl_squadron": "{n}. Staffel",
        "fl_alert": "Alarm",
        "fl_empty": "— frei —",
        "fl_propose": "Besetzung vorschlagen",
        "fl_apply": "Übernehmen",
        "fl_reset": "Zurücksetzen",
        "fl_hint": "Einen Piloten anklicken, dann einen zweiten, um sie zu tauschen.",
        "fl_cmd": "★ Schwarmführer. Welchen Schwarm oder welche Rotte Sie auch schicken – der ranghöchste Platz führt, deshalb werden Führer nach ihren Boni ausgewählt.",
        "fl_you": "Sie",
        "fl_applied": "{n} Piloten umgesetzt. Sicherung: {backup}",
        "fl_nochange": "Niemand wurde versetzt, es gibt nichts zu übernehmen.",
        "fl_ai": "KI",
        "fl_hurt": "verwundet",
        "fl_b_boost": "Boni",
        "fl_b_stats": "F/D/M",
        "fl_use_pool": "Reserve in den Vorschlag einbeziehen",
        "fl_bench_hint": "Hier einen Mann wählen, dann einen Platz anklicken: Er übernimmt Platz und Maschine, der Abgelöste geht in die Reserve. Einer für einen.",
        "fl_bench": "Reserve",
        "fl_none": "Diese Laufbahn hat keine Staffelaufstellung.",
        "fl_moved": "{n} versetzt",
        "tab_photo": "Eigenes Pilotenfoto",
        "photo_intro": "Wählen Sie ein JPG oder PNG. Der Helfer entfernt den Hintergrund lokal, setzt Sie vor den Porträthintergrund des Spiels und erstellt die DDS-Datei für diese Laufbahn. Schließen Sie IL-2 Korea vor dem Übernehmen oder Wiederherstellen.",
        "photo_current": "Aktuelles Porträt: {path}",
        "photo_none": "Kein Foto ausgewählt",
        "photo_choose": "Foto auswählen…",
        "photo_remove": "Hintergrund automatisch entfernen",
        "photo_working": "Hintergrund wird entfernt…",
        "photo_ready": "Ziehen Sie das Porträt an die gewünschte Stelle und passen Sie Zoom und Kantenbereinigung an.",
        "photo_drag": "Ziehen Sie das Porträt in der Vorschau an die gewünschte Stelle.",
        "photo_zoom": "Zoom",
        "photo_edge": "Kanten bereinigen",
        "photo_exposure": "Belichtung",
        "photo_contrast": "Kontrast",
        "photo_saturation": "Sättigung",
        "photo_sepia": "Sepiafilter",
        "photo_sepia_strength": "Sepia-Stärke",
        "photo_adjust_reset": "Anpassungen zurücksetzen",
        "photo_reset": "Position zurücksetzen",
        "photo_apply": "Für diese Laufbahn übernehmen",
        "photo_restore": "Originalfoto wiederherstellen",
        "photo_applied": "Eigenes Foto für {name} übernommen. DDS: {path}. Sicherung: {backup}",
        "photo_restored": "Originalfoto für {name} wiederhergestellt. Sicherung: {backup}",
        "photo_no_restore": "Für diese Laufbahn ist kein Originalfoto gespeichert.",
        "photo_filetypes": "Bilddateien",
        "tab_bio": "Biografie",
        "bio_intro": "Das Spiel zeigt die Biografie Ihres Piloten nur beim Anlegen einer Laufbahn. Hier können Sie sie neu schreiben; die Biografie in der Dienstakte zeigt dann Ihre Fassung. Text und Medaillen ändern nichts im Spiel und in der Laufbahndatei, das Spiel darf also geöffnet bleiben.",
        "bio_vars": "Platzhalter, die beim Anzeigen ausgefüllt werden - genau so schreiben: $[name] voller Name · $[firstName] Vorname · $[lastName] Nachname · $[birthDate] Geburtsdatum · $[startRank] Dienstgrad zu Beginn der Laufbahn. Zwischen Absätzen eine Leerzeile lassen.",
        "bio_source_game": "Dies ist die Biografie aus dem Spiel. Ändern und speichern macht sie zu Ihrer eigenen.",
        "bio_source_own": "Dies ist Ihre eigene Biografie, gespeichert am {date}.",
        "bio_count": "{n} von {max} Zeichen",
        "bio_medals": "Medaillen des Zweiten Weltkriegs",
        "bio_medals_nation": "Für chinesische und nordkoreanische Piloten gibt es keine Medaillen des Zweiten Weltkriegs zur Auswahl.",
        "bio_medal_none": "nicht verliehen",
        "bio_medal_plain": "Medaille",
        "bio_stars_hint": "★ = bronzener Service Star, einer je Feldzug",
        "bio_save": "Biografie speichern",
        "bio_restore": "Biografie des Spiels wiederherstellen",
        "bio_saved": "Biografie und Medaillen für {name} gespeichert. Öffnen Sie die Biografie in der Dienstakte erneut, um sie zu lesen.",
        "bio_restored": "Für {name} gelten wieder Biografie und Medaillen aus dem Spiel.",
        "bio_unknown": "Diese Platzhalter sind unbekannt und erscheinen genau so, wie sie geschrieben sind:\n{vars}\n\nTrotzdem speichern?",
        "bio_too_long": "Die Biografie ist {n} Zeichen lang; erlaubt sind {max}.",
        "bio_none": "Diese Laufbahn hat keine Biografie, von der aus Sie beginnen könnten.",
        "bio_boost": "Boni",
        "bio_boost_intro": "Ihr Pilot hat {total} Bonuspunkte: {bio} aus der Biografie und {promo} aus Beförderungen. Verteilen Sie sie beliebig neu, höchstens {max} auf eine Eigenschaft. Übernehmen schreibt in die Laufbahn: zuerst IL-2 Korea schließen. Es wird eine Sicherung angelegt.",
        "bio_boost_left": "Noch {n} von {total} Punkten zu verteilen",
        "bio_boost_done": "Alle {total} Punkte verteilt",
        "bio_boost_apply": "Boni übernehmen",
        "bio_boost_applied": "Die Boni von {name} sind jetzt {values}. Sicherung: {backup}",
        "bio_boost_unknown": "Die Spieldaten sagen nicht, wie viele Punkte diese Biografie gab, daher können ihre Boni nicht neu verteilt werden.",
        "fl_legend": "Die drei Zahlen sind die eigenen Werte des Piloten – Fähigkeiten / Disziplin / Mut – so wie sie sein Blatt zeigt. ↑ sind seine Boni. KI ist die Einstufung, die der erzeugte Einsatz ihm in der Luft gibt: seine Fähigkeiten, aber bei 4 gedeckelt – ein Pilot mit 5 fliegt also nicht besser als einer mit 4, und eine Verwundung kostet ihn eine Stufe.",
        "col_name": "Pilot", "col_state": "Schicksal", "col_date": "Verloren am", "col_can": "Zurückholbar",
        "kia": "gefallen", "mia": "vermisst",
        "yes": "ja", "no": "nein - die Laufbahn ist weitergegangen",
        "no_dead": "In dieser Laufbahn ist niemand verloren gegangen.",
        "restore_plane": "Auch sein Flugzeug wiederherstellen (sonst: abgesprungen, Flugzeug verloren)",
        "revive": "Zurückholen",
        "revive_confirm": "{name} wieder in die Aufstellung nehmen?",
        "revived": "{name} ist zurück in der Aufstellung. Sicherung: {backup}",
        "rule": "Ein Pilot kann am Tag seines Verlusts oder am Tag danach zurückgeholt werden, der eigene ebenso wie die Staffelkameraden. Heute ist der {date}.",
        "points_now": "Auszeichnungspunkte der Staffel: {points}",
        "points_add": "Hinzufügen",
        "points_added": "Die Auszeichnungspunkte betragen jetzt {points}. Sicherung: {backup}",
        "pending_intro": "Auszeichnungen, die Ihre Piloten erhalten haben, aber noch nicht verliehen bekamen. Jede kostet einen Auszeichnungspunkt. Klicken Sie eine Zeile an, um sie ein- oder auszuschließen, und verleihen Sie sie dann.",
        "pend_col_who": "Pilot",
        "pend_col_award": "Auszeichnung",
        "pend_col_earned": "Erworben",
        "pend_col_sk": "Können",
        "pend_col_di": "Disziplin",
        "pend_col_co": "Mut",
        "pend_col_after": "danach",
        "pend_all": "Alle",
        "pend_none": "Keine",
        "pend_grant": "Markierte verleihen",
        "pend_cost": "{n} markiert, {cost} von {points} Punkten",
        "pend_short": "Dafür sind {need} Auszeichnungspunkte nötig, die Staffel hat {points}. Bitte zuerst aufstocken.",
        "pend_done": "{n} Auszeichnungen verliehen, {spent} Punkte verbraucht. Sicherung: {backup}",
        "pend_col_status": "Status",
        "st_active": "einsatzbereit",
        "st_reserve": "Reserve",
        "st_notready": "nicht bereit",
        "st_wounded": "verwundet",
        "st_mia": "vermisst",
        "st_kia": "gefallen",
        "fl_unavailable": "{who} steht nicht zur Verfügung - {state}. Nur ein einsatzbereiter Pilot kann aufrücken.",
        "st_returning": "auf dem Rückweg",
        "locked": "Die Laufbahndatei ist in Benutzung - IL-2 Korea schließen und erneut versuchen.",
        "failed": "Das hat nicht geklappt: {error}",
        "player_note": "Der eigene Charakter des Spielers wird nicht aufgeführt: das Spiel führt die Laufbahn mit einem Nachfolger fort, und dieses Werkzeug lässt das unangetastet.",
        "refresh": "Aktualisieren",
        "tab_times": "Flugzeit",
        "times_intro": "Einsätze, deren Flugprotokoll einen Sprung zum Ziel zeigt - ein übersprungenes Stück der Strecke -, auf den Plan umgerechnet, so wie das Spiel es bei Einsätzen ohne Sie tut. Ein Einsatz, den Sie nur früher beendet haben und in dessen Protokoll kein Sprung steht, bleibt unverändert. Berechnen schreibt nur die eigene Aufzeichnung der Dienstakte; 'Übernehmen' trägt die angerechneten Stunden in die Laufbahn ein (Pilotenbildschirm, stundenabhängige Auszeichnungen), 'Zurücksetzen' nimmt sie wieder heraus.",
        "col_mission": "Einsatz",
        "col_flown": "Geflogen",
        "col_planned": "Geplant",
        "col_source": "Zeiten aus",
        "col_applied": "In der Laufbahn",
        "src_log": "Fluglog",
        "src_plan": "nur Plan",
        "applied": "übernommen",
        "not_applied": "—",
        "compute": "Berechnen",
        "computed": "{n} Einsätze umgerechnet; die Dienstakte zeigt sie mit eingeschaltetem Schalter.",
        "apply": "Angerechnete Stunden übernehmen",
        "restore": "Spielstunden zurücksetzen",
        "apply_confirm": "Die korrigierten Zeiten von {n} Einsatz/Einsätzen in die Laufbahn schreiben und sie ab jetzt korrigiert halten? Vorher wird gesichert.",
        "restore_confirm": "Die Originalzeiten des Spiels für alle {n} korrigierten Einsätze zurücksetzen und die Korrektur dieser Laufbahn beenden? Vorher wird gesichert.",
        "restore_awards": "{m} Auszeichnung(en) wurden allein durch die hinzugefügten Stunden verliehen und werden mit ihnen entzogen:",
        "restore_awards_done": "{m} Auszeichnung(en) entzogen.",
        "applied_done": "Angerechnete Stunden für {n} Einsätze übernommen. Sicherung: {backup}",
        "restored_done": "Spielstunden für {n} Einsätze wiederhergestellt. Sicherung: {backup}",
        "no_times": "Keine Einsätze mit Zeitsprung gefunden - entweder fliegen Sie die ganze Strecke, oder es wurde noch nichts geflogen.",
        "awards_since": "Seit dem Übernehmen der Stunden verliehene Auszeichnungen - die zu entziehenden ankreuzen (eine mit Abschüssen verdiente sollte bleiben):",
        "withdraw": "Angekreuzte Auszeichnungen entziehen",
        "auto_on": "Diese Laufbahn wird korrigiert gehalten: jeder ab jetzt geflogene Einsatz wird umgerechnet, sobald die Dienstakte die Laufbahn das nächste Mal liest (vorher Sicherung; übersprungen, solange das Spiel die Datei hält). Wiederherstellen setzt alle Originalwerte zurück und beendet das.",
        "auto_off": "Diese Laufbahn ist nicht korrigiert. Übernehmen schreibt die korrigierten Zeiten aller berechneten Einsätze und hält die Laufbahn von da an korrigiert.",
        "open_from_tracker": "Bitte öffnen Sie den Laufbahn-Helfer aus der Dienstakte - über die Schaltfläche in ihrer Kopfzeile.",
        "needs_mod": "Der Laufbahn-Helfer gehört zum Auszeichnungs-Mod. Installieren Sie die Mod-Komponente des Dienstakte-Setups und aktivieren Sie Modifikationen in IL-2 Korea.",
        "withdrawn": "{n} Auszeichnungen entzogen. Sicherung: {backup}",
        "the_squadron": "Die Staffel",
    },
    "es": {
        'tab_captured': 'Capturado',
        'captured_intro': 'Un piloto que saltó en paracaídas o aterrizó forzosamente sobre terreno enemigo: el juego le deja volver al escuadrón en un par de días. Márquelo como capturado en su lugar: el juego lo trata entonces como una baja (para el jugador: «Comandante capturado», con un nuevo comandante que asignar). Solo cuenta la última salida de cada piloto.',
        'col_sortie': 'Salida',
        'col_fate': 'Destino',
        'col_can2': 'Posible',
        'fate_evading': 'evadiéndose, de vuelta el {date}',
        'fate_lost_plane': 'avión perdido, piloto de vuelta',
        'no_later': 'no - ha volado desde entonces',
        'no_candidates': 'Nadie ha caído sobre terreno enemigo en esta carrera.',
        'capture': 'Marcar como capturado',
        'capture_confirm': '¿Marcar a {name} como capturado el {date}? El juego lo listará como desaparecido en combate.',
        'captured_done': '{name} figura ahora como desaparecido en combate: capturado. Copia de seguridad: {backup}',
        "title": "Asistente de carrera IL-2 Korea",
        "subtitle": "La oficina del escuadrón para IL-2 Sturmovik: Korea",
        "career": "Carrera",
        "no_game": "No se encontró ninguna instalación de IL-2 Korea.",
        "no_careers": "No se encontraron carreras.",
        "tab_revive": "Recuperar a un piloto",
        "tab_points": "Puntos de condecoración",
        "tab_flights": "Patrullas",
        "fl_intro": "Quién se sienta dónde. Una patrulla son cuatro aviones, una sección dos. Quien ocupe el puesto de número más bajo de los que envíe manda toda la misión, y sus tres bonificaciones cubren a todos los pilotos que van en ella; las de los demás no cuentan. Como cualquier patrulla o sección puede ser la que envíe, son los puestos de mando los que deben llevar las bonificaciones. Pulse un piloto y después otro para intercambiarlos; el avión acompaña a su piloto.",
        "fl_c1": "1 · Rojo",
        "fl_c2": "2 · Azul",
        "fl_c3": "3 · Verde",
        "fl_c4": "4 · Amarillo",
        "fl_c5": "5 · Blanco",
        "fl_c6": "6 · Negro",
        "fl_num": "Vuelo {n}",
        "fl_commander": "Vuelo del mando",
        "fl_squadron": "{n}.º Escuadrón",
        "fl_alert": "alerta",
        "fl_empty": "— libre —",
        "fl_propose": "Proponer una formación",
        "fl_apply": "Aplicar",
        "fl_reset": "Empezar de nuevo",
        "fl_hint": "Pulse un piloto y después otro para intercambiarlos.",
        "fl_cmd": "★ jefe de patrulla. Sea cual sea la patrulla o sección que envíe, su puesto más antiguo toma el mando, por eso los jefes se eligen por sus bonificaciones.",
        "fl_you": "usted",
        "fl_applied": "{n} pilotos reubicados. Copia de seguridad: {backup}",
        "fl_nochange": "Nadie se ha movido, no hay nada que aplicar.",
        "fl_ai": "IA",
        "fl_hurt": "herido",
        "fl_b_boost": "Bonif.",
        "fl_b_stats": "H/D/V",
        "fl_use_pool": "que la propuesta recurra a la reserva",
        "fl_bench_hint": "Elija aquí a un piloto y pulse un puesto: ocupa el puesto y su avión, y el sustituido pasa a la reserva. Uno por uno.",
        "fl_bench": "Reserva",
        "fl_none": "Esta carrera no tiene formación que mostrar.",
        "fl_moved": "{n} movidos",
        "tab_photo": "Foto de piloto personalizada",
        "photo_intro": "Elija un JPG o PNG. La herramienta elimina el fondo localmente, coloca el retrato sobre el fondo del juego y crea el DDS para esta carrera. Cierre IL-2 Korea antes de aplicar o restaurar.",
        "photo_current": "Retrato actual: {path}",
        "photo_none": "Ninguna foto seleccionada",
        "photo_choose": "Elegir foto…",
        "photo_remove": "Eliminar el fondo automáticamente",
        "photo_working": "Eliminando el fondo…",
        "photo_ready": "Arrastre el retrato para colocarlo y ajuste el zoom y la limpieza de bordes.",
        "photo_drag": "Arrastre la vista previa para colocar el retrato.",
        "photo_zoom": "Zoom",
        "photo_edge": "Limpieza de bordes",
        "photo_exposure": "Exposición",
        "photo_contrast": "Contraste",
        "photo_saturation": "Saturación",
        "photo_sepia": "Filtro sepia",
        "photo_sepia_strength": "Intensidad sepia",
        "photo_adjust_reset": "Restablecer ajustes",
        "photo_reset": "Restablecer posición",
        "photo_apply": "Aplicar a esta carrera",
        "photo_restore": "Restaurar foto original",
        "photo_applied": "Foto personalizada aplicada a {name}. DDS: {path}. Copia de seguridad: {backup}",
        "photo_restored": "Foto original restaurada para {name}. Copia de seguridad: {backup}",
        "photo_no_restore": "No hay un registro de la foto original para esta carrera.",
        "photo_filetypes": "Archivos de imagen",
        "tab_bio": "Biografía",
        "bio_intro": "El juego muestra la biografía de su piloto solo al crear una carrera. Aquí puede reescribirla; la biografía de la Hoja de Servicios mostrará entonces su versión. El texto y las medallas no cambian nada en el juego ni en el archivo de la carrera, así que el juego puede seguir abierto.",
        "bio_vars": "Marcadores que se rellenan al mostrar la biografía; escríbalos exactamente así: $[name] nombre completo · $[firstName] nombre · $[lastName] apellido · $[birthDate] fecha de nacimiento · $[startRank] rango al inicio de la carrera. Deje una línea vacía entre párrafos.",
        "bio_source_game": "Esta es la biografía del juego. Modifíquela y guárdela para que sea suya.",
        "bio_source_own": "Esta es su propia biografía, guardada el {date}.",
        "bio_count": "{n} de {max} caracteres",
        "bio_medals": "Medallas de la Segunda Guerra Mundial",
        "bio_medals_nation": "Los pilotos chinos y norcoreanos no tienen medallas de la Segunda Guerra Mundial para elegir.",
        "bio_medal_none": "no concedida",
        "bio_medal_plain": "medalla",
        "bio_stars_hint": "★ = estrella de servicio de bronce, una por campaña",
        "bio_save": "Guardar biografía",
        "bio_restore": "Restaurar la biografía del juego",
        "bio_saved": "Biografía y medallas guardadas para {name}. Vuelva a abrir la biografía en la Hoja de Servicios para leerla.",
        "bio_restored": "{name} vuelve a tener la biografía y las medallas del juego.",
        "bio_unknown": "Estos marcadores no se conocen y aparecerán tal como están escritos:\n{vars}\n\n¿Guardar de todos modos?",
        "bio_too_long": "La biografía tiene {n} caracteres; el límite es {max}.",
        "bio_none": "Esta carrera no tiene una biografía de la que partir.",
        "bio_boost": "Potenciadores",
        "bio_boost_intro": "Su piloto tiene {total} puntos de potenciador: {bio} de su biografía y {promo} de ascensos. Repártalos de nuevo como quiera, como máximo {max} en un atributo. Aplicar escribe en la carrera: cierre antes IL-2 Korea. Se crea una copia de seguridad.",
        "bio_boost_left": "Quedan {n} de {total} puntos por repartir",
        "bio_boost_done": "Los {total} puntos están repartidos",
        "bio_boost_apply": "Aplicar potenciadores",
        "bio_boost_applied": "Los potenciadores de {name} son ahora {values}. Copia de seguridad: {backup}",
        "bio_boost_unknown": "Los datos del juego no indican cuántos puntos dio esta biografía, así que sus potenciadores no se pueden repartir de nuevo.",
        "fl_legend": "Los tres números son las aptitudes propias del piloto: habilidad / disciplina / valor, tal como aparecen en su ficha. ↑ son sus bonificaciones. IA es la categoría que la misión generada le asigna en vuelo: su habilidad, pero limitada a 4, de modo que un piloto de 5 no vuela mejor que uno de 4, y una herida le cuesta un nivel.",
        "col_name": "Piloto", "col_state": "Suerte", "col_date": "Perdido el", "col_can": "Recuperable",
        "kia": "muerto en combate", "mia": "desaparecido en combate",
        "yes": "sí", "no": "no: la carrera ya ha avanzado",
        "no_dead": "Nadie se ha perdido en esta carrera.",
        "restore_plane": "Restaurar también su avión (si no: saltó en paracaídas, avión perdido)",
        "revive": "Recuperar",
        "revive_confirm": "¿Devolver a {name} a la alineación?",
        "revived": "{name} vuelve a estar en la alineación. Copia de seguridad: {backup}",
        "rule": "Un piloto puede recuperarse el día en que se perdió o el día siguiente, tanto el tuyo como tus compañeros de escuadrón. Hoy es {date}.",
        "points_now": "Puntos de condecoración del escuadrón: {points}",
        "points_add": "Añadir",
        "points_added": "Los puntos de condecoración son ahora {points}. Copia de seguridad: {backup}",
        "pending_intro": "Condecoraciones que sus pilotos han ganado pero aún no han recibido. Cada una cuesta un punto. Pulse una línea para incluirla o excluirla y después entréguelas.",
        "pend_col_who": "Piloto",
        "pend_col_award": "Condecoración",
        "pend_col_earned": "Ganada",
        "pend_col_sk": "Pericia",
        "pend_col_di": "Disciplina",
        "pend_col_co": "Valor",
        "pend_col_after": "después",
        "pend_all": "Todas",
        "pend_none": "Ninguna",
        "pend_grant": "Entregar las marcadas",
        "pend_cost": "{n} marcadas, {cost} de {points} puntos",
        "pend_short": "Hacen falta {need} puntos de condecoración y el escuadrón tiene {points}. Añada algunos primero.",
        "pend_done": "{n} condecoraciones entregadas, {spent} puntos gastados. Copia de seguridad: {backup}",
        "pend_col_status": "Estado",
        "st_active": "activo",
        "st_reserve": "reserva",
        "st_notready": "no listo",
        "st_wounded": "herido",
        "st_mia": "desaparecido",
        "st_kia": "muerto",
        "fl_unavailable": "{who} no está disponible: {state}. Solo puede ascender un piloto apto para el servicio.",
        "st_returning": "regresando a pie",
        "locked": "El archivo de la carrera está en uso: cierre IL-2 Korea e inténtelo de nuevo.",
        "failed": "No ha funcionado: {error}",
        "player_note": "El personaje del jugador no aparece: el juego continúa la carrera con un sucesor y esta herramienta no lo toca.",
        "refresh": "Actualizar",
        "tab_times": "Tiempo de vuelo",
        "times_intro": "Misiones cuyo registro de vuelo muestra un salto hasta el objetivo - parte de la ruta omitida -, ajustadas al plan como hace el juego con las misiones voladas sin usted. Una salida que usted simplemente terminó antes, sin ningún salto en su registro, se deja como está. Calcular solo escribe el registro propio de la Hoja de Servicios; 'Aplicar' escribe las horas acreditadas en la carrera (pantalla del piloto, condecoraciones por horas) y 'Restaurar' las retira.",
        "col_mission": "Misión",
        "col_flown": "Volado",
        "col_planned": "Previsto",
        "col_source": "Tiempos según",
        "col_applied": "En la carrera",
        "src_log": "registro de vuelo",
        "src_plan": "solo plan",
        "applied": "aplicado",
        "not_applied": "—",
        "compute": "Calcular",
        "computed": "{n} misiones ajustadas; la Hoja de Servicios las muestra con el interruptor activado.",
        "apply": "Aplicar horas acreditadas",
        "restore": "Restaurar horas del juego",
        "apply_confirm": "¿Escribir los tiempos corregidos de {n} misión(es) en la carrera y mantenerla corregida a partir de ahora? Antes se hace una copia de seguridad.",
        "restore_confirm": "¿Devolver los tiempos originales del juego a las {n} misiones corregidas y dejar de corregir esta carrera? Antes se hace una copia de seguridad.",
        "restore_awards": "{m} condecoración(es) se obtuvieron solo por las horas añadidas y se retirarán con ellas:",
        "restore_awards_done": "{m} condecoración(es) retirada(s).",
        "applied_done": "Horas acreditadas aplicadas a {n} misiones. Copia de seguridad: {backup}",
        "restored_done": "Horas del juego restauradas en {n} misiones. Copia de seguridad: {backup}",
        "no_times": "No se encontraron misiones con salto: o vuela toda la ruta, o aún no se ha volado nada.",
        "awards_since": "Condecoraciones concedidas desde que se aplicaron las horas - marque las que quiera retirar (una ganada por derribos debería quedarse):",
        "withdraw": "Retirar las marcadas",
        "auto_on": "Esta carrera se mantiene corregida: cada misión volada a partir de ahora se recalcula cuando la Hoja de Servicios vuelva a leer la carrera (copia de seguridad previa; se omite mientras el juego tenga el archivo abierto). Restaurar devuelve todos los originales y pone fin a esto.",
        "auto_off": "Esta carrera no está corregida. Aplicar escribe los tiempos corregidos de todas las misiones calculadas y mantiene la carrera corregida desde entonces.",
        "open_from_tracker": "Abra el Asistente de carrera desde la Hoja de Servicios: el botón de su cabecera.",
        "needs_mod": "El Asistente de carrera forma parte del mod de condecoraciones. Instale el componente del mod en el instalador de la Hoja de Servicios y active las modificaciones en IL-2 Korea.",
        "withdrawn": "{n} condecoraciones retiradas. Copia de seguridad: {backup}",
        "the_squadron": "El escuadrón",
    },
    "fr": {
        'tab_captured': 'Capturé',
        'captured_intro': 'Un pilote qui a sauté ou s’est posé en catastrophe en territoire ennemi : le jeu le laisse regagner l’escadron en quelques jours. Marquez-le plutôt comme capturé : le jeu le traite alors comme une perte (pour le joueur : « Commandant capturé », avec un nouveau commandant à nommer). Seule la dernière sortie d’un pilote compte.',
        'col_sortie': 'Sortie',
        'col_fate': 'Sort',
        'col_can2': 'Possible',
        'fate_evading': 'en évasion, de retour le {date}',
        'fate_lost_plane': 'appareil perdu, pilote rentré',
        'no_later': 'non - il a volé depuis',
        'no_candidates': 'Personne n’est tombé en territoire ennemi dans cette carrière.',
        'capture': 'Marquer comme capturé',
        'capture_confirm': 'Marquer {name} comme capturé le {date} ? Le jeu le portera disparu au combat.',
        'captured_done': '{name} est désormais porté disparu - capturé. Sauvegarde : {backup}',
        "title": "Assistant de carrière IL-2 Korea",
        "subtitle": "Le bureau de l’escadron pour IL-2 Sturmovik: Korea",
        "career": "Carrière",
        "no_game": "Aucune installation d’IL-2 Korea trouvée.",
        "no_careers": "Aucune carrière trouvée.",
        "tab_revive": "Ramener un pilote",
        "tab_points": "Points de décoration",
        "tab_flights": "Patrouilles",
        "fl_intro": "Qui occupe quelle place. Une patrouille compte quatre appareils, une section deux. Celui qui occupe la place au numéro le plus bas parmi celles que vous envoyez commande toute la mission, et ses trois bonus s’appliquent à chacun de ses pilotes — ceux des autres ne comptent pas. Comme n’importe quelle patrouille ou section peut être celle que vous envoyez, ce sont les places de chef qui doivent porter les bonus. Cliquez sur un pilote, puis sur un autre, pour les échanger ; l’appareil suit son pilote.",
        "fl_c1": "1 · Rouge",
        "fl_c2": "2 · Bleu",
        "fl_c3": "3 · Vert",
        "fl_c4": "4 · Jaune",
        "fl_c5": "5 · Blanc",
        "fl_c6": "6 · Noir",
        "fl_num": "Patrouille {n}",
        "fl_commander": "Patrouille du commandant",
        "fl_squadron": "{n}e Escadrille",
        "fl_alert": "alerte",
        "fl_empty": "— libre —",
        "fl_propose": "Proposer une répartition",
        "fl_apply": "Appliquer",
        "fl_reset": "Recommencer",
        "fl_hint": "Cliquez sur un pilote, puis sur un autre, pour les échanger.",
        "fl_cmd": "★ chef de patrouille. Quelle que soit la patrouille ou la section envoyée, sa place la plus ancienne prend le commandement : les chefs sont donc choisis sur leurs bonus.",
        "fl_you": "vous",
        "fl_applied": "{n} pilotes replacés. Sauvegarde : {backup}",
        "fl_nochange": "Personne n’a bougé, il n’y a rien à appliquer.",
        "fl_ai": "IA",
        "fl_hurt": "blessé",
        "fl_b_boost": "Bonus",
        "fl_b_stats": "C/D/C",
        "fl_use_pool": "autoriser la proposition à puiser dans la réserve",
        "fl_bench_hint": "Choisissez un pilote ici, puis cliquez sur une place : il la prend avec son appareil, et celui qu’il remplace passe en réserve. Un pour un.",
        "fl_bench": "Réserve",
        "fl_none": "Cette carrière n’a aucune formation à afficher.",
        "fl_moved": "{n} déplacés",
        "tab_photo": "Photo de pilote personnalisée",
        "photo_intro": "Choisissez un JPG ou PNG. L’utilitaire supprime le fond localement, place le portrait sur le fond du jeu et crée le DDS de cette carrière. Fermez IL-2 Korea avant d’appliquer ou de restaurer.",
        "photo_current": "Portrait actuel : {path}",
        "photo_none": "Aucune photo sélectionnée",
        "photo_choose": "Choisir une photo…",
        "photo_remove": "Supprimer automatiquement le fond",
        "photo_working": "Suppression du fond…",
        "photo_ready": "Faites glisser le portrait, puis ajustez le zoom et le nettoyage des contours.",
        "photo_drag": "Faites glisser l’aperçu pour placer le portrait.",
        "photo_zoom": "Zoom",
        "photo_edge": "Nettoyage des contours",
        "photo_exposure": "Exposition",
        "photo_contrast": "Contraste",
        "photo_saturation": "Saturation",
        "photo_sepia": "Filtre sépia",
        "photo_sepia_strength": "Intensité du sépia",
        "photo_adjust_reset": "Réinitialiser les réglages",
        "photo_reset": "Réinitialiser la position",
        "photo_apply": "Appliquer à cette carrière",
        "photo_restore": "Restaurer la photo d’origine",
        "photo_applied": "Photo personnalisée appliquée à {name}. DDS : {path}. Sauvegarde : {backup}",
        "photo_restored": "Photo d’origine restaurée pour {name}. Sauvegarde : {backup}",
        "photo_no_restore": "Aucune photo d’origine n’est enregistrée pour cette carrière.",
        "photo_filetypes": "Fichiers image",
        "tab_bio": "Biographie",
        "bio_intro": "Le jeu n’affiche la biographie de votre pilote qu’à la création d’une carrière. Vous pouvez la réécrire ici ; la biographie de l’état de service affichera alors votre version. Le texte et les médailles ne changent rien dans le jeu ni dans le fichier de carrière : le jeu peut rester ouvert.",
        "bio_vars": "Variables remplies à l’affichage de la biographie ; écrivez-les exactement ainsi : $[name] nom complet · $[firstName] prénom · $[lastName] nom de famille · $[birthDate] date de naissance · $[startRank] grade au début de la carrière. Laissez une ligne vide entre les paragraphes.",
        "bio_source_game": "Voici la biographie du jeu. Modifiez-la et enregistrez-la pour en faire la vôtre.",
        "bio_source_own": "Voici votre propre biographie, enregistrée le {date}.",
        "bio_count": "{n} sur {max} caractères",
        "bio_medals": "Médailles de la Seconde Guerre mondiale",
        "bio_medals_nation": "Les pilotes chinois et nord-coréens n’ont pas de médailles de la Seconde Guerre mondiale à choisir.",
        "bio_medal_none": "non décernée",
        "bio_medal_plain": "médaille",
        "bio_stars_hint": "★ = étoile de service en bronze, une par campagne",
        "bio_save": "Enregistrer la biographie",
        "bio_restore": "Rétablir la biographie du jeu",
        "bio_saved": "Biographie et médailles enregistrées pour {name}. Rouvrez la biographie dans l’état de service pour la lire.",
        "bio_restored": "{name} a de nouveau la biographie et les médailles du jeu.",
        "bio_unknown": "Ces variables sont inconnues et apparaîtront telles qu’écrites :\n{vars}\n\nEnregistrer quand même ?",
        "bio_too_long": "La biographie compte {n} caractères ; la limite est de {max}.",
        "bio_none": "Cette carrière n’a pas de biographie de départ.",
        "bio_boost": "Bonus",
        "bio_boost_intro": "Votre pilote a {total} points de bonus : {bio} de sa biographie et {promo} de promotions. Répartissez-les à nouveau comme vous le souhaitez, au plus {max} sur un attribut. Appliquer écrit dans la carrière : fermez d’abord IL-2 Korea. Une sauvegarde est créée.",
        "bio_boost_left": "Encore {n} points sur {total} à répartir",
        "bio_boost_done": "Les {total} points sont répartis",
        "bio_boost_apply": "Appliquer les bonus",
        "bio_boost_applied": "Les bonus de {name} sont maintenant {values}. Sauvegarde : {backup}",
        "bio_boost_unknown": "Les données du jeu n’indiquent pas combien de points cette biographie a donnés ; ses bonus ne peuvent donc pas être répartis à nouveau.",
        "fl_legend": "Les trois nombres sont les qualités propres du pilote — compétence / discipline / courage — telles que sa fiche les affiche. ↑ ce sont ses bonus. IA est le niveau que la mission générée lui donne en vol : sa compétence, mais plafonnée à 4, si bien qu’un pilote à 5 ne vole pas mieux qu’un pilote à 4, et une blessure lui coûte un niveau.",
        "col_name": "Pilote", "col_state": "Sort", "col_date": "Perdu le", "col_can": "Récupérable",
        "kia": "mort au combat", "mia": "porté disparu",
        "yes": "oui", "no": "non - la carrière a continué",
        "no_dead": "Personne n’a été perdu dans cette carrière.",
        "restore_plane": "Rétablir aussi son avion (sinon : sauté en parachute, avion perdu)",
        "revive": "Ramener",
        "revive_confirm": "Remettre {name} dans l’ordre de bataille ?",
        "revived": "{name} est de retour dans l’ordre de bataille. Sauvegarde : {backup}",
        "rule": "Un pilote peut être ramené le jour de sa perte ou le lendemain, le vôtre comme vos camarades d’escadrille. Nous sommes le {date}.",
        "points_now": "Points de décoration de l’escadron : {points}",
        "points_add": "Ajouter",
        "points_added": "Les points de décoration sont maintenant à {points}. Sauvegarde : {backup}",
        "pending_intro": "Décorations que vos pilotes ont méritées mais pas encore reçues. Chacune coûte un point. Cliquez sur une ligne pour l’inclure ou l’exclure, puis remettez-les.",
        "pend_col_who": "Pilote",
        "pend_col_award": "Décoration",
        "pend_col_earned": "Méritée",
        "pend_col_sk": "Habileté",
        "pend_col_di": "Discipline",
        "pend_col_co": "Courage",
        "pend_col_after": "après",
        "pend_all": "Toutes",
        "pend_none": "Aucune",
        "pend_grant": "Remettre les décorations cochées",
        "pend_cost": "{n} cochées, {cost} points sur {points}",
        "pend_short": "Il faut {need} points de décoration et l’escadron en a {points}. Ajoutez-en d’abord.",
        "pend_done": "{n} décorations remises, {spent} points dépensés. Sauvegarde : {backup}",
        "pend_col_status": "Statut",
        "st_active": "actif",
        "st_reserve": "réserve",
        "st_notready": "indisponible",
        "st_wounded": "blessé",
        "st_mia": "disparu",
        "st_kia": "tué",
        "fl_unavailable": "{who} n’est pas disponible : {state}. Seul un pilote apte au service peut être appelé.",
        "st_returning": "sur le chemin du retour",
        "locked": "Le fichier de carrière est en cours d’utilisation : fermez IL-2 Korea et réessayez.",
        "failed": "Cela n’a pas fonctionné : {error}",
        "player_note": "Le personnage du joueur n’est pas listé : le jeu poursuit la carrière avec un successeur, et cet outil n’y touche pas.",
        "refresh": "Actualiser",
        "tab_times": "Temps de vol",
        "times_intro": "Missions dont le journal de vol montre un saut vers l’objectif - une partie du trajet passée -, recalées sur le plan comme le jeu le fait pour les missions volées sans vous. Une sortie que vous avez simplement terminée plus tôt, sans aucun saut dans son journal, est laissée telle quelle. Calculer n’écrit que le registre propre de l’état de service ; « Appliquer » inscrit les heures créditées dans la carrière (écran du pilote, décorations aux heures) et « Rétablir » les retire.",
        "col_mission": "Mission",
        "col_flown": "Volé",
        "col_planned": "Prévu",
        "col_source": "Temps d’après",
        "col_applied": "Dans la carrière",
        "src_log": "journal de vol",
        "src_plan": "plan seul",
        "applied": "appliqué",
        "not_applied": "—",
        "compute": "Calculer",
        "computed": "{n} missions recalées ; l’état de service les affiche avec l’interrupteur activé.",
        "apply": "Appliquer les heures créditées",
        "restore": "Rétablir les heures du jeu",
        "apply_confirm": "Écrire les temps corrigés de {n} mission(s) dans la carrière et la maintenir corrigée désormais ? Une sauvegarde est faite d’abord.",
        "restore_confirm": "Remettre les temps d’origine du jeu pour les {n} missions corrigées et cesser de corriger cette carrière ? Une sauvegarde est faite d’abord.",
        "restore_awards": "{m} décoration(s) n’ont été obtenues que par les heures ajoutées et seront retirées avec elles :",
        "restore_awards_done": "{m} décoration(s) retirée(s).",
        "applied_done": "Heures créditées appliquées à {n} missions. Sauvegarde : {backup}",
        "restored_done": "Heures du jeu rétablies pour {n} missions. Sauvegarde : {backup}",
        "no_times": "Aucune mission avec saut trouvée : soit vous volez toute la route, soit rien n’a encore été volé.",
        "awards_since": "Décorations attribuées depuis l’application des heures - cochez celles à retirer (une décoration gagnée par des victoires doit rester) :",
        "withdraw": "Retirer les décorations cochées",
        "auto_on": "Cette carrière est maintenue corrigée : chaque mission volée désormais est recalée quand l’état de service relit la carrière (sauvegarde d’abord ; ignoré tant que le jeu tient le fichier). Restaurer remet tous les originaux et y met fin.",
        "auto_off": "Cette carrière n’est pas corrigée. Appliquer écrit les temps corrigés de toutes les missions calculées et maintient la carrière corrigée à partir de là.",
        "open_from_tracker": "Ouvrez l’assistant de carrière depuis l’état de service : le bouton de son en-tête.",
        "needs_mod": "L’assistant de carrière fait partie du mod de décorations. Installez le composant mod de l’installateur de l’état de service et activez les modifications dans IL-2 Korea.",
        "withdrawn": "{n} décorations retirées. Sauvegarde : {backup}",
        "the_squadron": "L’escadron",
    },
    "ru": {
        'tab_captured': 'В плену',
        'captured_intro': 'Лётчик, выпрыгнувший с парашютом или севший на вынужденную над территорией противника: игра даёт ему вернуться в часть через пару дней. Вместо этого отметьте его пленённым — игра посчитает это потерей (для игрока: «Командир взят в плен», нужно назначить нового командира). Учитывается только последний вылет лётчика.',
        'col_sortie': 'Вылет',
        'col_fate': 'Судьба',
        'col_can2': 'Возможно',
        'fate_evading': 'выходит к своим, вернётся {date}',
        'fate_lost_plane': 'самолёт потерян, лётчик вернулся',
        'no_later': 'нет — он летал после этого',
        'no_candidates': 'В этой карьере никто не был сбит над территорией противника.',
        'capture': 'Отметить как пленённого',
        'capture_confirm': 'Отметить {name} пленённым {date}? Игра будет считать его пропавшим без вести.',
        'captured_done': '{name} теперь числится пропавшим без вести — в плену. Резервная копия: {backup}',
        "title": "Помощник карьеры IL-2 Korea",
        "subtitle": "Канцелярия эскадрильи для IL-2 Sturmovik: Korea",
        "career": "Карьера",
        "no_game": "Установка IL-2 Korea не найдена.",
        "no_careers": "Карьеры не найдены.",
        "tab_revive": "Вернуть лётчика",
        "tab_points": "Наградные очки",
        "tab_flights": "Звенья",
        "fl_intro": "Кто где сидит. Звено — четыре самолёта, пара — два. Тот, кто занимает место с наименьшим номером из вылетающих, командует всем вылетом, и его три надбавки распространяются на каждого лётчика в группе — чужие не учитываются. Поскольку вылететь может любое звено или любая пара, надбавки важны именно на ведущих местах. Щёлкните по лётчику, затем по другому, чтобы поменять их местами; самолёт следует за своим лётчиком.",
        "fl_c1": "1 · Красное",
        "fl_c2": "2 · Синее",
        "fl_c3": "3 · Зелёное",
        "fl_c4": "4 · Жёлтое",
        "fl_c5": "5 · Белое",
        "fl_c6": "6 · Чёрное",
        "fl_num": "Звено {n}",
        "fl_commander": "Звено управления",
        "fl_squadron": "{n}-я эскадрилья",
        "fl_alert": "дежурное",
        "fl_empty": "— свободно —",
        "fl_propose": "Предложить расстановку",
        "fl_apply": "Применить",
        "fl_reset": "Начать заново",
        "fl_hint": "Щёлкните по лётчику, затем по другому, чтобы поменять их местами.",
        "fl_cmd": "★ ведущий звена. Какое бы звено или пару вы ни отправили, командует старшее место в ней, поэтому ведущих подбирают по надбавкам.",
        "fl_you": "вы",
        "fl_applied": "Переставлено лётчиков: {n}. Резервная копия: {backup}",
        "fl_nochange": "Никто не переставлен, применять нечего.",
        "fl_ai": "ИИ",
        "fl_hurt": "ранен",
        "fl_b_boost": "Надбавки",
        "fl_b_stats": "М/Д/С",
        "fl_use_pool": "разрешить брать людей из резерва",
        "fl_bench_hint": "Выберите здесь лётчика, затем щёлкните по месту: он занимает его вместе с самолётом, а тот, кого он сменил, уходит в резерв. Один на одного.",
        "fl_bench": "Резерв",
        "fl_none": "В этой карьере нет строевого состава.",
        "fl_moved": "переставлено: {n}",
        "tab_photo": "Собственное фото лётчика",
        "photo_intro": "Выберите JPG или PNG. Помощник локально удалит фон, поместит портрет на фон игры и создаст DDS для этой карьеры. Перед применением или восстановлением закройте IL-2 Korea.",
        "photo_current": "Текущий портрет: {path}",
        "photo_none": "Фото не выбрано",
        "photo_choose": "Выбрать фото…",
        "photo_remove": "Автоматически удалить фон",
        "photo_working": "Фон удаляется…",
        "photo_ready": "Перетащите портрет на нужное место, затем настройте масштаб и очистку краёв.",
        "photo_drag": "Перетащите портрет в окне просмотра.",
        "photo_zoom": "Масштаб",
        "photo_edge": "Очистка краёв",
        "photo_exposure": "Экспозиция",
        "photo_contrast": "Контраст",
        "photo_saturation": "Насыщенность",
        "photo_sepia": "Фильтр «Сепия»",
        "photo_sepia_strength": "Интенсивность сепии",
        "photo_adjust_reset": "Сбросить настройки",
        "photo_reset": "Сбросить положение",
        "photo_apply": "Применить к этой карьере",
        "photo_restore": "Вернуть исходное фото",
        "photo_applied": "Собственное фото применено для {name}. DDS: {path}. Резервная копия: {backup}",
        "photo_restored": "Исходное фото восстановлено для {name}. Резервная копия: {backup}",
        "photo_no_restore": "Для этой карьеры нет записи об исходном фото.",
        "photo_filetypes": "Файлы изображений",
        "tab_bio": "Биография",
        "bio_intro": "Игра показывает биографию лётчика только при создании карьеры. Здесь её можно переписать; биография в послужном списке будет показывать вашу версию. Текст и медали ничего не меняют в игре и в файле карьеры, поэтому игру можно не закрывать.",
        "bio_vars": "Подстановки, которые заполняются при показе биографии, — пишите их именно так: $[name] полное имя · $[firstName] имя · $[lastName] фамилия · $[birthDate] дата рождения · $[startRank] звание в начале карьеры. Между абзацами оставляйте пустую строку.",
        "bio_source_game": "Это биография из игры. Измените и сохраните её, чтобы она стала вашей.",
        "bio_source_own": "Это ваша собственная биография, сохранённая {date}.",
        "bio_count": "{n} из {max} символов",
        "bio_medals": "Медали Второй мировой войны",
        "bio_medals_nation": "Для китайских и северокорейских лётчиков медалей Второй мировой войны нет.",
        "bio_medal_none": "не вручена",
        "bio_medal_plain": "медаль",
        "bio_stars_hint": "★ = бронзовая звезда за участие, по одной за кампанию",
        "bio_save": "Сохранить биографию",
        "bio_restore": "Вернуть биографию из игры",
        "bio_saved": "Биография и медали для {name} сохранены. Откройте биографию в послужном списке заново, чтобы прочитать её.",
        "bio_restored": "У {name} снова биография и медали из игры.",
        "bio_unknown": "Эти подстановки неизвестны и будут показаны так, как написаны:\n{vars}\n\nВсё равно сохранить?",
        "bio_too_long": "Длина биографии — {n} символов; предел — {max}.",
        "bio_none": "У этой карьеры нет биографии, от которой можно оттолкнуться.",
        "bio_boost": "Бустеры",
        "bio_boost_intro": "Очки бустеров вашего лётчика: {total} — {bio} из биографии и {promo} за повышения. Распределите их заново как угодно, не больше {max} на одно качество. Применение записывает в карьеру: сначала закройте IL-2 Korea. Создаётся резервная копия.",
        "bio_boost_left": "Осталось распределить {n} из {total} очков",
        "bio_boost_done": "Все {total} очка распределены",
        "bio_boost_apply": "Применить бустеры",
        "bio_boost_applied": "Бустеры {name} теперь {values}. Резервная копия: {backup}",
        "bio_boost_unknown": "В данных игры не указано, сколько очков дала эта биография, поэтому её бустеры нельзя распределить заново.",
        "fl_legend": "Три числа — собственные качества лётчика: мастерство / дисциплина / смелость, в том же порядке, что и в его карточке. ↑ — его надбавки. ИИ — оценка, которую сгенерированный вылет даёт ему в воздухе: его мастерство, но не выше 4 — так что лётчик с 5 летает не лучше, чем с 4, а ранение стоит ему одной ступени.",
        "col_name": "Лётчик", "col_state": "Судьба", "col_date": "Потерян", "col_can": "Можно вернуть",
        "kia": "погиб", "mia": "пропал без вести",
        "yes": "да", "no": "нет — карьера ушла дальше",
        "no_dead": "В этой карьере никто не потерян.",
        "restore_plane": "Вернуть и его самолёт (иначе: выпрыгнул с парашютом, самолёт потерян)",
        "revive": "Вернуть",
        "revive_confirm": "Вернуть {name} в строй?",
        "revived": "{name} снова в строю. Резервная копия: {backup}",
        "rule": "Лётчика можно вернуть в день его потери или на следующий день — как своего, так и товарищей по эскадрилье. Сегодня {date}.",
        "points_now": "Наградные очки эскадрильи: {points}",
        "points_add": "Добавить",
        "points_added": "Наградных очков теперь {points}. Резервная копия: {backup}",
        "pending_intro": "Награды, заслуженные вашими лётчиками, но ещё не вручённые. Каждая стоит одно наградное очко. Щёлкните по строке, чтобы включить или исключить её, затем вручите.",
        "pend_col_who": "Лётчик",
        "pend_col_award": "Награда",
        "pend_col_earned": "Заслужена",
        "pend_col_sk": "Навык",
        "pend_col_di": "Дисциплина",
        "pend_col_co": "Смелость",
        "pend_col_after": "после",
        "pend_all": "Все",
        "pend_none": "Ни одной",
        "pend_grant": "Вручить отмеченные",
        "pend_cost": "отмечено {n}, {cost} очков из {points}",
        "pend_short": "Нужно {need} наградных очков, у эскадрильи {points}. Сначала добавьте.",
        "pend_done": "Вручено наград: {n}, потрачено очков: {spent}. Резервная копия: {backup}",
        "pend_col_status": "Состояние",
        "st_active": "в строю",
        "st_reserve": "резерв",
        "st_notready": "не готов",
        "st_wounded": "ранен",
        "st_mia": "пропал без вести",
        "st_kia": "погиб",
        "fl_unavailable": "{who} недоступен — {state}. Поднять можно только годного к вылету лётчика.",
        "st_returning": "возвращается",
        "locked": "Файл карьеры занят — закройте IL-2 Korea и попробуйте снова.",
        "failed": "Не получилось: {error}",
        "player_note": "Персонаж игрока не показан: игра продолжает карьеру преемником, и этот инструмент этого не трогает.",
        "refresh": "Обновить",
        "tab_times": "Лётное время",
        "times_intro": "Вылеты, в журнале которых виден скачок к цели — пропущенная часть маршрута, — пересчитанные по плану, как игра делает для вылетов без вас. Вылет, просто завершённый раньше срока, без скачка в журнале, остаётся без изменений. «Рассчитать» пишет только собственную запись послужного списка; «Применить» вносит зачтённые часы в карьеру (экран лётчика, награды за часы), «Вернуть» убирает их.",
        "col_mission": "Вылет",
        "col_flown": "Налёт",
        "col_planned": "По плану",
        "col_source": "Время из",
        "col_applied": "В карьере",
        "src_log": "журнала полёта",
        "src_plan": "только плана",
        "applied": "применено",
        "not_applied": "—",
        "compute": "Рассчитать",
        "computed": "Пересчитано вылетов: {n}; послужной список показывает их при включённом переключателе.",
        "apply": "Применить зачтённые часы",
        "restore": "Вернуть часы игры",
        "apply_confirm": "Записать исправленное время {n} вылет(ов) в карьеру и держать её исправленной с этого момента? Сначала будет сделана резервная копия.",
        "restore_confirm": "Вернуть исходное время игры для всех {n} исправленных вылетов и прекратить исправление этой карьеры? Сначала будет сделана резервная копия.",
        "restore_awards": "{m} наград(ы) были получены только за добавленные часы и будут отозваны вместе с ними:",
        "restore_awards_done": "Отозвано наград: {m}.",
        "applied_done": "Зачтённые часы применены к {n} вылетам. Резервная копия: {backup}",
        "restored_done": "Часы игры возвращены для {n} вылетов. Резервная копия: {backup}",
        "no_times": "Вылетов с перемоткой не найдено — либо вы летаете весь маршрут, либо ещё ничего не налётано.",
        "awards_since": "Награды, вручённые после применения часов — отметьте те, что нужно отозвать (заслуженная сбитыми должна остаться):",
        "withdraw": "Отозвать отмеченные",
        "auto_on": "Эта карьера держится исправленной: каждый вылет, совершённый с этого момента, пересчитывается, когда послужной список в следующий раз читает карьеру (сначала резервная копия; пропускается, пока файл занят игрой). «Восстановить» возвращает все исходные значения и прекращает это.",
        "auto_off": "Эта карьера не исправлена. «Применить» записывает исправленное время всех рассчитанных вылетов и с этого момента держит карьеру исправленной.",
        "open_from_tracker": "Откройте помощник карьеры из послужного списка — кнопкой в его шапке.",
        "needs_mod": "Помощник карьеры — часть мода наград. Установите компонент мода в установщике послужного списка и включите модификации в IL-2 Korea.",
        "withdrawn": "Отозвано наград: {n}. Резервная копия: {backup}",
        "the_squadron": "Эскадрилья",
    },
    "zh": {
        'tab_captured': '被俘',
        'captured_intro': '在敌方地域跳伞或迫降的飞行员：游戏会让他在几天后自行返回中队。可改为将其标记为被俘——游戏随后按损失处理（对玩家而言：“指挥官被俘”，需指定新指挥官）。只计入飞行员的最后一次出击。',
        'col_sortie': '出击',
        'col_fate': '下落',
        'col_can2': '可行',
        'fate_evading': '正在归队，{date} 返回',
        'fate_lost_plane': '飞机损失，飞行员已返回',
        'no_later': '否——此后他仍有出击',
        'no_candidates': '本生涯中无人在敌方地域坠落。',
        'capture': '标记为被俘',
        'capture_confirm': '将 {name} 标记为于 {date} 被俘？游戏将把他列为作战失踪。',
        'captured_done': '{name} 现已列为作战失踪——被俘。备份：{backup}',
        "title": "IL-2 Korea 生涯助手",
        "subtitle": "IL-2 Sturmovik: Korea 中队文书",
        "career": "生涯",
        "no_game": "未找到 IL-2 Korea 安装。",
        "no_careers": "未找到生涯。",
        "tab_revive": "复活飞行员",
        "tab_points": "授勋点数",
        "tab_flights": "编队",
        "fl_intro": "谁坐哪个位置。一个小队四架飞机，一个分队两架。所派出的位置中编号最小的那一位指挥整次任务，他的三项加成覆盖队中每一位飞行员——其他人的加成不计。由于任何小队或分队都可能被派出，因此加成真正重要的是长机位置。点击一名飞行员，再点击另一名即可交换；座机随飞行员一同调动。",
        "fl_c1": "1 · 红队",
        "fl_c2": "2 · 蓝队",
        "fl_c3": "3 · 绿队",
        "fl_c4": "4 · 黄队",
        "fl_c5": "5 · 白队",
        "fl_c6": "6 · 黑队",
        "fl_num": "第 {n} 编队",
        "fl_commander": "指挥官飞行小队",
        "fl_squadron": "第{n}中队",
        "fl_alert": "待命",
        "fl_empty": "— 空缺 —",
        "fl_propose": "生成建议编排",
        "fl_apply": "应用",
        "fl_reset": "重新开始",
        "fl_hint": "点击一名飞行员，再点击另一名即可交换。",
        "fl_cmd": "★ 长机。无论派出哪个小队或分队，都由其中位次最高者指挥，所以长机按加成挑选。",
        "fl_you": "您",
        "fl_applied": "已调整 {n} 名飞行员。备份：{backup}",
        "fl_nochange": "没有人被调动，无需应用。",
        "fl_ai": "AI",
        "fl_hurt": "负伤",
        "fl_b_boost": "加成",
        "fl_b_stats": "技/律/勇",
        "fl_use_pool": "允许建议编排动用预备队",
        "fl_bench_hint": "在此选中一名飞行员，再点击一个位置：他接手该位置及其座机，被替下的人进入预备队。一换一。",
        "fl_bench": "预备队",
        "fl_none": "该生涯没有可显示的编队。",
        "fl_moved": "已移动 {n} 人",
        "tab_photo": "自定义飞行员照片",
        "photo_intro": "选择 JPG 或 PNG。助手会在本机移除背景，将人物放到游戏肖像背景上，并为此生涯创建 DDS。应用或恢复前请关闭 IL-2 Korea。",
        "photo_current": "当前肖像：{path}",
        "photo_none": "尚未选择照片",
        "photo_choose": "选择照片…",
        "photo_remove": "自动移除背景",
        "photo_working": "正在移除背景…",
        "photo_ready": "拖动肖像调整位置，然后调整缩放和边缘清理。",
        "photo_drag": "拖动预览中的肖像以调整位置。",
        "photo_zoom": "缩放",
        "photo_edge": "边缘清理",
        "photo_exposure": "曝光",
        "photo_contrast": "对比度",
        "photo_saturation": "饱和度",
        "photo_sepia": "棕褐色滤镜",
        "photo_sepia_strength": "棕褐色强度",
        "photo_adjust_reset": "重置调整",
        "photo_reset": "重置位置",
        "photo_apply": "应用到此生涯",
        "photo_restore": "恢复原始照片",
        "photo_applied": "已为 {name} 应用自定义照片。DDS：{path}。备份：{backup}",
        "photo_restored": "已为 {name} 恢复原始照片。备份：{backup}",
        "photo_no_restore": "此生涯没有原始照片记录。",
        "photo_filetypes": "图像文件",
        "tab_bio": "生平",
        "bio_intro": "游戏只在创建生涯时显示飞行员的生平。您可以在这里重写它；服役记录中的生平随后会显示您的版本。文字和奖章不会改变游戏或生涯文件，因此无需关闭游戏。",
        "bio_vars": "显示生平时会自动填写的占位符，请严格按此书写：$[name] 全名 · $[firstName] 名 · $[lastName] 姓 · $[birthDate] 出生日期 · $[startRank] 生涯开始时的军衔。段落之间请空一行。",
        "bio_source_game": "这是游戏自带的生平。修改并保存后即成为您自己的版本。",
        "bio_source_own": "这是您自己的生平，保存于 {date}。",
        "bio_count": "{n} / {max} 个字符",
        "bio_medals": "第二次世界大战奖章",
        "bio_medals_nation": "中国和朝鲜飞行员没有可选择的第二次世界大战奖章。",
        "bio_medal_none": "未授予",
        "bio_medal_plain": "奖章",
        "bio_stars_hint": "★ = 铜质服役星，每次战役一颗",
        "bio_save": "保存生平",
        "bio_restore": "恢复游戏自带的生平",
        "bio_saved": "已为 {name} 保存生平和奖章。请在服役记录中重新打开生平以阅读。",
        "bio_restored": "{name} 已恢复游戏自带的生平和奖章。",
        "bio_unknown": "以下占位符无法识别，将按原样显示：\n{vars}\n\n仍要保存吗？",
        "bio_too_long": "生平长度为 {n} 个字符；上限为 {max}。",
        "bio_none": "此生涯没有可作为起点的生平。",
        "bio_boost": "加成",
        "bio_boost_intro": "您的飞行员共有 {total} 点加成：生平提供 {bio} 点，晋升获得 {promo} 点。可任意重新分配，每项属性最多 {max} 点。应用会写入生涯：请先关闭 IL-2 Korea。会先创建备份。",
        "bio_boost_left": "还有 {n} / {total} 点待分配",
        "bio_boost_done": "{total} 点已全部分配",
        "bio_boost_apply": "应用加成",
        "bio_boost_applied": "{name} 的加成现在为 {values}。备份：{backup}",
        "bio_boost_unknown": "游戏数据未说明此生平提供了多少点，因此无法重新分配其加成。",
        "fl_legend": "三个数字是飞行员自身的技能 / 纪律 / 勇气，与他的面板显示一致。↑ 是他的加成。AI 是生成的任务对他空中表现的评级：取决于技能，但上限为 4 —— 所以技能 5 的飞行员并不比 4 的飞得好，而负伤会降一级。",
        "col_name": "飞行员", "col_state": "结局", "col_date": "损失日期", "col_can": "可复活",
        "kia": "阵亡", "mia": "失踪",
        "yes": "是", "no": "否——生涯已进入下一天",
        "no_dead": "此生涯中无人损失。",
        "restore_plane": "同时恢复他的飞机（否则：跳伞，飞机损失）",
        "revive": "复活",
        "revive_confirm": "让 {name} 重返编队？",
        "revived": "{name} 已重返编队。备份：{backup}",
        "rule": "飞行员可在损失当天或次日复活，您本人的飞行员与僚机飞行员同样如此。今天是 {date}。",
        "points_now": "中队当前授勋点数：{points}",
        "points_add": "增加",
        "points_added": "授勋点数现为 {points}。备份：{backup}",
        "pending_intro": "您的飞行员已获得但尚未授予的奖励。每项消耗一点授勋点数。点击某行以选中或取消，然后予以授予。",
        "pend_col_who": "飞行员",
        "pend_col_award": "奖励",
        "pend_col_earned": "获得日期",
        "pend_col_sk": "技能",
        "pend_col_di": "纪律",
        "pend_col_co": "勇气",
        "pend_col_after": "之后",
        "pend_all": "全选",
        "pend_none": "全不选",
        "pend_grant": "授予已选奖励",
        "pend_cost": "已选 {n} 项，{cost} / {points} 点",
        "pend_short": "需要 {need} 点授勋点数，中队只有 {points} 点。请先补充。",
        "pend_done": "已授予 {n} 项奖励，消耗 {spent} 点。备份：{backup}",
        "pend_col_status": "状态",
        "st_active": "可出击",
        "st_reserve": "预备",
        "st_notready": "未就绪",
        "st_wounded": "负伤",
        "st_mia": "失踪",
        "st_kia": "阵亡",
        "fl_unavailable": "{who} 无法出勤——{state}。只有可执行任务的飞行员才能调入现役。",
        "st_returning": "正在返回途中",
        "locked": "生涯文件正在使用中——请关闭 IL-2 Korea 后重试。",
        "failed": "操作失败：{error}",
        "player_note": "玩家自己的角色不在列表中：游戏会以继任者延续生涯，本工具不作改动。",
        "refresh": "刷新",
        "tab_times": "飞行时间",
        "times_intro": "飞行日志中出现跳跃至目标（跳过部分航线）的任务，按计划重新计时，如同游戏对无您参与的任务所做。仅仅提前结束、日志中没有跳跃的出击则保持不变。“计算”只写入服役记录自己的记录；“应用”把计入的小时数写入生涯（飞行员界面、按小时授予的奖励），“恢复”则将其撤回。",
        "col_mission": "任务",
        "col_flown": "实飞",
        "col_planned": "计划",
        "col_source": "计时来源",
        "col_applied": "已写入生涯",
        "src_log": "飞行日志",
        "src_plan": "仅计划",
        "applied": "已应用",
        "not_applied": "—",
        "compute": "计算",
        "computed": "已重新计时 {n} 个任务；打开开关后服役记录将显示。",
        "apply": "应用计入的小时数",
        "restore": "恢复游戏小时数",
        "apply_confirm": "将 {n} 个任务的修正时间写入生涯并从此保持修正状态？会先备份。",
        "restore_confirm": "还原全部 {n} 个已修正任务的游戏原始时间并停止修正此生涯？会先备份。",
        "restore_awards": "有 {m} 项奖励仅凭添加的小时数获得，将随之撤销：",
        "restore_awards_done": "已撤销 {m} 项奖励。",
        "applied_done": "已将计入小时数应用于 {n} 个任务。备份：{backup}",
        "restored_done": "已恢复 {n} 个任务的游戏小时数。备份：{backup}",
        "no_times": "未找到跳跃任务——您要么飞完了全程，要么尚未出击。",
        "awards_since": "应用小时数后授予的奖励——勾选要撤销的（凭击落获得的应保留）：",
        "withdraw": "撤销勾选的奖励",
        "auto_on": "此生涯保持修正状态：从现在起飞行的每个任务都会在服役记录下次读取生涯时重新计时（先备份；游戏占用文件时跳过）。“恢复”会还原全部原始值并结束此状态。",
        "auto_off": "此生涯未修正。“应用”会写入所有已计算任务的修正时间，并从此保持生涯为修正状态。",
        "open_from_tracker": "请从服役记录中打开生涯助手——其页眉中的按钮。",
        "needs_mod": "生涯助手是奖励模组的一部分。请在服役记录安装程序中安装模组组件，并在 IL-2 Korea 中启用修改。",
        "withdrawn": "已撤销 {n} 项奖励。备份：{backup}",
        "the_squadron": "中队",
    },
}


# The game's own word for each part of a line-up, in the player's own
# language. Taking these from the game rather than translating them here
# means Career Helper and the Combat Units screen call the same thing by
# the same name - Stabsschwarm, Звено управления, 指挥官飞行小队 - and
# there is no term for us to get wrong.
GAME_LANGS = {"en": "eng", "de": "ger", "es": "spa",
              "fr": "fra", "ru": "rus", "zh": "chs"}


def game_labels(lang: str) -> Dict[str, str]:
    """
    Commander Flight, 1st/2nd/3rd Squadron, Flight N, Section N.

    Returns {} if the file cannot be read, and every caller falls back to
    its own string, so a missing locale costs a word and not a crash.
    """
    try:
        text = AssetResolver(find_game_dir()).read_text(
            f"nsdata/assets/locale/career.locale={GAME_LANGS.get(lang, 'eng')}.json")
        return loads_lenient(text) if text else {}
    except Exception:            # noqa: BLE001 - a label is never worth failing over
        return {}


class Group(NamedTuple):
    """One headed block of seats on the board."""
    label: str
    start: int
    size: int
    row: int                     # which row of the board it sits on
    col: int                     # and which column within that row
    row_label: str = ""          # a heading spanning the row, on its first block


def line_up_blocks(country: int, seats: int) -> List[tuple]:
    """
    Where each block of seats begins and how many it holds, as (start, size).

    The single source of truth for the board's arithmetic. A seat's flight,
    its section and whether it leads are all its position within its own
    block - never slot % 4, which is only right when the blocks begin at 0,
    4, 8. An eastern regiment's flights begin at 2, 6, 10, so slot % 4 put
    the lead star two seats into every flight.
    """
    if country not in (501, 502, 503):
        return [(f * 4, 4) for f in range(max(6, seats // 4))]
    blocks = [(0, 2)]
    squadrons = max(3, -(-(max(0, seats - 2)) // 12))
    for s in range(squadrons):
        blocks += [(2 + s * 12 + f * 4, 4) for f in range(3)]
    return blocks


def seat_position(blocks: List[tuple], slot: int) -> tuple:
    """(block number, index within it) for a seat."""
    for n, (start, size) in enumerate(blocks):
        if start <= slot < start + size:
            return n, slot - start
    return len(blocks) - 1, 0


def line_up_shape(country: int, seats: int, t: Dict[str, str],
                  game: Optional[Dict[str, str]] = None) -> List[Group]:
    """
    How this air force arranges its line-up, as headed blocks of seats.

    Two shapes, both measured rather than assumed. The American squadron
    is 24 seats in six flights of four, all in one row - which is what the
    game draws and what this chart has always drawn.

    The eastern regiment is a commander pair and three squadrons of twelve,
    each squadron three flights of four: 38 seats. Proved against a Chinese
    career by matching the game's Combat Units screen to the database name
    by name - slots 0-1 the commander and his wingman, 2-13 the 1st
    Squadron, 14-19 the six men of the 2nd it had at the time. That the 3rd
    Squadron is 26-37 follows by extension and has not been seen occupied.

    The squadrons are laid out two to a row, under the commander pair:

        Commander Flight
        1st Squadron          2nd Squadron
        3rd Squadron          (4th, if a unit ever has one)

    Six columns, the same width as the American board the window is already
    sized for, and half the height of one squadron per row. The game sets
    all of its squadrons side by side and scrolls horizontally to reach
    them; two rows shows the whole regiment without scrolling sideways.
    """
    game = game or {}
    flight_word = game.get("carFlightNum") or t.get("fl_num") or "Flight $[value]"

    def flight_label(n: int) -> str:
        return flight_word.replace("$[value]", str(n)).replace("{n}", str(n))

    blocks = line_up_blocks(country, seats)
    if country not in (501, 502, 503):
        # Six flights of four, named for their colours as the game names them.
        return [Group(t.get(f"fl_c{f + 1}") or flight_label(f + 1), start, size, 0, f)
                for f, (start, size) in enumerate(blocks)]

    # The game's German calls a squadron and a flight the same thing -
    # carSquadron1 is "Schwarm 1" and carFlightNum is "Schwarm $[value]" -
    # so heading a column "Schwarm 1" inside a row headed "Schwarm 1" says
    # nothing. Where the game's own two words collide, its flight word is
    # kept for the columns and ours is used for the row.
    collides = (game.get("carSquadron1") or "") == flight_label(1)

    def squadron_label(n: int) -> str:
        if not collides:
            named = game.get(f"carSquadron{n}")
            if named:
                return named
        return t["fl_squadron"].format(n=n)

    groups = [Group(game.get("carCommanderFlight") or t["fl_commander"], 0, 2, 0, 0)]
    squadrons = max(3, -(-(max(0, seats - 2)) // 12))
    for s in range(squadrons):
        for f in range(3):
            groups.append(Group(flight_label(f + 1), 2 + s * 12 + f * 4, 4,
                                1 + s // 2, (s % 2) * 3 + f,
                                squadron_label(s + 1) if f == 0 else ""))
    return groups


def pick_language() -> str:
    """The tracker's saved language, else the system's, else English."""
    try:
        code = Settings(default_cache_dir().parent).language()
        if code in STRINGS:
            return code
    except Exception:            # noqa: BLE001 - any failure means "no preference"
        pass
    sys_lang = (locale.getlocale()[0] or "").lower()
    for code in STRINGS:
        if sys_lang.startswith(code):
            return code
    return "en"


# ---------------------------------------------------------------------------
# The career file
# ---------------------------------------------------------------------------

class Career:
    def __init__(self, path: Path):
        self.path = path
        self.name = path.stem

    def _open(self, write: bool = False) -> sqlite3.Connection:
        uri = f"file:{self.path}?mode={'rw' if write else 'ro'}"
        con = sqlite3.connect(uri, uri=True, timeout=1.0)
        con.row_factory = sqlite3.Row
        return con

    def current_date(self) -> str:
        with self._open() as con:
            return con.execute("SELECT currentDate FROM career").fetchone()[0]

    def yesterday(self) -> str:
        """The career date one day back, or today's if the date will not parse."""
        today = self.current_date()
        try:
            return (datetime.strptime(today[:10], "%Y.%m.%d")
                    - timedelta(days=1)).strftime("%Y.%m.%d")
        except ValueError:
            return today[:10]

    def player_ids(self) -> set:
        with self._open() as con:
            ids = {r[0] for r in con.execute("SELECT id FROM pilot WHERE isPlayer=1")}
            ids.add(con.execute("SELECT playerId FROM career").fetchone()[0])
            return ids

    def lost_pilots(self) -> List[Dict]:
        """
        KIA and MIA pilots, and whether they can still be brought back.

        The player is on this list. He used not to be, which made the
        Captured tab a one-way door: it will mark the player's own pilot
        missing - it has no exclusion - and there was then no way back
        through the interface for the one pilot a career cannot do without.

        The window is the day of the loss and the one after it, the same
        for everybody. One day, because the mistake this tab exists to
        undo is usually noticed one click too late - the man is marked,
        End Day is pressed out of habit, and the career has moved on. Only
        one day, because a pilot brought back later walks into a squadron
        whose war went on without him: days of sorties he was not on,
        losses he did not see. That is worse than the hole he leaves.
        """
        today = self.current_date()[:10]
        cutoff = self.yesterday()
        players = self.player_ids()
        out = []
        with self._open() as con:
            rows = con.execute(
                "SELECT id, name, lastName, rankId, state, stateDate FROM pilot "
                "WHERE isDeleted=0 AND state IN (2, 3) ORDER BY stateDate DESC, id")
            for r in rows:
                is_player = r["id"] in players
                lost_on = (r["stateDate"] or "")[:10]
                out.append({
                    "id": r["id"],
                    "name": f"{r['name']} {r['lastName']}".strip(),
                    "state": r["state"],
                    "lost_on": lost_on,
                    "player": is_player,
                    "revivable": lost_on in (today, cutoff),
                })
        return out

    def downed_pilots(self) -> List[Dict]:
        """
        Pilots who went down over enemy ground and are still on the roll:
        the game's evaders (state 1, walking back) and anyone whose aircraft
        was lost on a sortie he survived. Capturable only while that sortie
        is his latest - he has not flown since.
        """
        out = []
        with self._open() as con:
            latest = {r["pilotId"]: r["id"] for r in con.execute(
                "SELECT pilotId, MAX(id) AS id FROM sortie WHERE isDeleted=0 GROUP BY pilotId")}
            rows = con.execute(
                """SELECT s.id, s.pilotId, s.missionId, s.status, s.planeStatus, s.date,
                          p.name, p.lastName, p.state, p.stateEndDate
                   FROM sortie s JOIN pilot p ON p.id = s.pilotId
                   WHERE s.isDeleted=0 AND p.isDeleted=0 AND p.state IN (0, 1)
                     AND (s.status = 1 OR s.planeStatus = 3) AND s.status NOT IN (2, 3)
                   ORDER BY s.date DESC, s.id DESC""")
            for r in rows:
                out.append({
                    "id": r["id"], "pilot_id": r["pilotId"], "mission_id": r["missionId"],
                    "name": f"{r['name']} {r['lastName']}".strip(),
                    "date": (r["date"] or "")[:10],
                    "evading": r["state"] == 1 and latest.get(r["pilotId"]) == r["id"],
                    "back_on": (r["stateEndDate"] or "")[:10],
                    "capturable": latest.get(r["pilotId"]) == r["id"],
                })
        return out

    # -- flight-time corrections -------------------------------------------

    def corrections(self):
        return corrections.load(self.name)

    def compute_corrections(self, game: Path):
        data = corrections.compute(self.path, game, existing=corrections.load(self.name))
        corrections.save(self.name, data)
        return data

    # A career is either corrected or not, never half: applying writes every
    # computed mission and sets the standing order, so each mission flown
    # afterwards is re-timed when the tracker next reads the career;
    # restoring puts every original back and ends the order.
    def apply_hours(self):
        backup = self.backup()
        data = corrections.load(self.name) or {"format": corrections.FORMAT, "career": self.name, "missions": {}}
        keys = [k for k, e in data["missions"].items() if not e.get("applied")]
        done = corrections.apply_hours(self.path, data, keys)
        data["auto"] = True
        corrections.save(self.name, data)
        return backup, done

    def hour_awards(self, game: Optional[Path]):
        """Awards since the correction that only the added hours earned."""
        data = corrections.load(self.name)
        cfg = None
        if game is not None:
            from korea_service_record.gamedata import AwardsConfig
            path = game / "data" / "scg" / "2" / "awards.cfg"
            if path.is_file():
                cfg = AwardsConfig(path)
        return corrections.hour_awards(self.path, data, cfg) if data and cfg else []

    def restore_hours(self, game: Optional[Path] = None):
        """Every original back; the awards the added hours alone earned are
        taken back with them, since the hours that earned them are gone."""
        backup = self.backup()
        data = corrections.load(self.name) or {"missions": {}}
        withdrawn = self.hour_awards(game)
        keys = [k for k, e in data["missions"].items() if e.get("applied")]
        done = corrections.restore_hours(self.path, data, keys)
        for a in withdrawn:
            corrections.withdraw_award(self.path, a["id"])
        data["auto"] = False
        corrections.save(self.name, data)
        return backup, done, withdrawn

    def award_points(self) -> int:
        with self._open() as con:
            return int(con.execute("SELECT awardPoints FROM squadron").fetchone()[0] or 0)

    # -- pending awards -----------------------------------------------------
    # An award earned but not yet handed over sits at isPending=1 with a
    # receivedDate of '0000.00.00', and costs a point from the squadron's
    # pool. The player's own are presented at the rollover; the ones that
    # pile up are his pilots', and in game they are given one at a time.

    # improvedQual records WHICH attribute the presentation improved, as a
    # 1-based index in the PANEL's order - not the order of the persLevel
    # nibbles, which is skills, courage, discipline low to high. 2 and 3
    # cross over. Proven in game 2026-09-24: an award written 2 moved
    # discipline, one written 3 moved courage.
    QUAL = {1: ("skills", 0), 2: ("discipline", 2), 3: ("courage", 1)}
    QUAL_CAP = 4                      # stored 4, drawn as 5

    def attributes(self, pilot_ids=None) -> Dict[int, tuple]:
        """
        Skill, discipline and courage per pilot, as the game's own panel
        prints them.

        persLevel packs the three into nibbles - 0 skill, 1 courage,
        2 discipline - each stored one lower than it is shown, which is why
        every value here is the nibble plus one. leadLevel, which holds the
        boosters, is deliberately not read: a decoration does not move them.
        Promotions do.
        """
        sql = "SELECT id, persLevel FROM pilot WHERE isDeleted=0"
        params: tuple = ()
        if pilot_ids:
            ids = [int(i) for i in pilot_ids]
            sql += " AND id IN (%s)" % ",".join("?" * len(ids))
            params = tuple(ids)
        with self._open() as con:
            rows = con.execute(sql, params).fetchall()
        out = {}
        for r in rows:
            v = int(r["persLevel"] or 0)
            out[r["id"]] = ((v & 15) + 1, ((v >> 8) & 15) + 1, ((v >> 4) & 15) + 1)
        return out

    def pending_awards(self, game: Optional[Path] = None) -> List[Dict]:
        """
        Every award earned and not yet presented, by pilot.

        Everyone, including the dead: a posthumous award is a real thing
        and the game offers them too. Each line carries the man's standing,
        and the killed and the missing come in unticked and in red, so
        presenting to them is a decision taken rather than one slipped past.

        Decorations only. A promotion is an award row too - category 1,
        one of the 6019xx pseudo-awards - and it sits pending exactly like
        a medal, so it used to appear here and could be handed over with
        everything else. That is wrong in every particular: presenting it
        bumps a random skill, courage or discipline instead of raising the
        rank, writes a type-20 event where the game writes type 19, spends
        an award point, and never touches the booster.

        The booster is the reason this belongs to the game and not here.
        Its own Award and promotion screen says what each does:

            "Awarding a medal will randomly improve one of the pilot's
             skills"
            "Select the pilot booster you wish to enhance"

        A decoration rolls the attribute, which is what present_awards
        below imitates; a promotion is a choice the player makes. Since
        2026-09-29 both can be actioned on the day they are earned, so
        there is nothing the game makes you wait for and nothing to be
        gained by doing it here.
        """
        names = {}
        if game is not None:
            from korea_service_record.gamedata import AwardsConfig
            path = game / "data" / "scg" / "2" / "awards.cfg"
            if path.is_file():
                names = {a.award_id: a.name for a in AwardsConfig(path).definitions.values()}
        with self._open() as con:
            rows = con.execute(
                """SELECT a.id, a.type, a.cost, a.earnedDate, a.pilotId,
                          p.name, p.lastName, p.persLevel, p.state, p.slot
                   FROM award a JOIN pilot p ON p.id=a.pilotId
                   WHERE a.isPending=1 AND a.isDeleted=0 AND a.pilotId>0
                     AND a.category<>1
                     AND p.isDeleted=0
                   ORDER BY p.lastName, p.name, a.earnedDate, a.id""").fetchall()
        return [{"id": r["id"], "type": r["type"], "cost": int(r["cost"] or 1),
                 "earned": r["earnedDate"], "pilot": r["pilotId"],
                 "who": f"{r['name']} {r['lastName']}".strip(),
                 "status": self._pilot_status(r["state"], r["slot"]),
                 "award": names.get(r["type"], str(r["type"]))} for r in rows]

    @staticmethod
    def _pilot_status(state: int, slot: int) -> str:
        """
        Where a man stands, in the terms the game's own screens use.

        state first, because it outranks the slot: 1 walking home after going
        down, 2 killed, 3 missing, 4 in hospital. Then the slot bands - the
        line-up, 1000..1999 parked with an aircraft under repair, which the
        Combat units screen calls "in reserve - NOT READY", and 2000..4999
        the replacement pool.
        """
        state, slot = int(state or 0), int(slot or 0)
        if state == 1:
            return "returning"
        if state == 2:
            return "kia"
        if state == 3:
            return "mia"
        if state == 4:
            return "wounded"
        if 1000 <= slot < 2000:
            return "notready"
        if 2000 <= slot < 5000:
            return "reserve"
        return "active"

    def present_awards(self, award_ids: List[int]) -> Dict[str, Any]:
        """
        Hand the chosen awards over, exactly as the game does it.

        Per award: isPending 0, receivedDate today, a random attribute +1
        unless the man is already at the cap, and one type-20 event with
        ipar3=1 carrying the award ROW id. The squadron pays a point each.
        """
        import random
        ids = [int(i) for i in award_ids]
        if not ids:
            return {"granted": 0, "spent": 0, "backup": None}
        backup = self.backup()
        marks = ",".join("?" * len(ids))
        with self._open(write=True) as con:
            con.execute("BEGIN IMMEDIATE")
            career = con.execute("SELECT id, currentDate, currentTime FROM career").fetchone()
            points = int(con.execute("SELECT awardPoints FROM squadron").fetchone()[0] or 0)
            rows = con.execute(
                f"""SELECT id, type, cost, pilotId, pilotRank, squadronId
                    FROM award WHERE id IN ({marks}) AND isPending=1 AND isDeleted=0
                      AND category<>1""",
                ids).fetchall()
            need = sum(int(r["cost"] or 1) for r in rows)
            if need > points:
                con.rollback()
                raise ValueError(f"{need}/{points}")
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            levels = {}
            for r in rows:
                pid = r["pilotId"]
                if pid not in levels:
                    levels[pid] = int(con.execute(
                        "SELECT persLevel FROM pilot WHERE id=?", (pid,)).fetchone()[0] or 0)
                # a bump goes to an attribute that is not already at the cap;
                # when all three are full the game writes 0 and moves nothing
                free = [q for q, (_, nib) in self.QUAL.items()
                        if (levels[pid] >> 4 * nib) & 15 < self.QUAL_CAP]
                qual = random.choice(free) if free else 0
                if qual:
                    levels[pid] += 1 << (4 * self.QUAL[qual][1])
                    con.execute("UPDATE pilot SET persLevel=? WHERE id=?", (levels[pid], pid))
                con.execute(
                    "UPDATE award SET isPending=0, receivedDate=?, improvedQual=? WHERE id=?",
                    (career["currentDate"], qual, r["id"]))
                con.execute(
                    """INSERT INTO event (date, type, pilotId, rankId, missionId, squadronId,
                                          careerId, planeId, ipar1, ipar2, ipar3, ipar4,
                                          tpar1, tpar2, tpar3, tpar4, insdate, isDeleted)
                       VALUES (?, 20, ?, ?, -1, ?, ?, -1, ?, ?, 1, -1, '', '', '', '', ?, 0)""",
                    (career["currentTime"], pid, r["pilotRank"], r["squadronId"],
                     career["id"], r["id"], r["type"], now))
            con.execute("UPDATE squadron SET awardPoints = awardPoints - ?", (need,))
            con.commit()
        return {"granted": len(rows), "spent": need, "backup": backup}

    # -- flights -------------------------------------------------------------
    # The line-up is 24 seats: six flights of four, each flight two sections
    # of two. flight = slot // 4, section = slot // 2, and flight 6 (slots
    # 20-23) is the alert flight the game scrambles for unplanned missions.
    # Read off the Combat Units screen and confirmed against the database.
    #
    # A pilot's aircraft travels with him. Swapping two men in game moved
    # both pilot.slot and plane.slot, so Galt kept FF-117 rather than
    # inheriting the seat's aeroplane. A reseat here has to move the pair or
    # somebody ends up in a wreck.

    SEATS = 24                           # the American establishment
    EAST_SEATS = 38                      # commander pair + three squadrons of twelve
    FLIGHTS = 6
    BENCH_BASE = 1000                    # at or above this a man is off the board
    PARK = 9000                          # scratch slots while a permutation lands

    # Fatigue is deliberately absent. It exists in the database and runs 0 to
    # 9 - a sortie adds one, a day on the ground takes one back - but nothing
    # reads it. Every reference to the key string is a write, every
    # instruction touching pilot+0x244 is the increment, the decrement or the
    # database, no other binary queries the pilot table, and nothing in the
    # generated mission varies with it: men at 6 still fly as AILevel 4. The
    # game does not even show it. Seating on a number with no consumer would
    # be advice dressed up as arithmetic.
    LEAD_MIN_AI = 3                      # nobody duller leads a flight

    @staticmethod
    def parse_watchmen(value: str) -> set:
        """
        The seats standing alert, from ``squadron.watchmen``.

        The game's D flight defaults to flight 6 but the player may put it on
        any seats, so it must be read rather than assumed. The field is a list
        like ``slot|20|21|22|23`` and ``slot`` is the only prefix the engine
        writes - there is no section or flight form in the binary. Duty
        belongs to the *seats*, not the men, so reseating changes who stands
        alert without touching this field.
        """
        parts = (value or "").split("|")
        if len(parts) < 2 or parts[0].strip() != "slot":
            return set()
        return {int(x) for x in parts[1:] if x.strip().isdigit()}

    def alert_slots(self) -> set:
        with self._open() as con:
            row = con.execute("SELECT watchmen FROM squadron").fetchone()
        return self.parse_watchmen(row[0] if row else "")

    @staticmethod
    def ai_level(skills: int, health: int, state: int) -> int:
        """
        The AILevel the generated mission will give this pilot.

        Fitted to every pilot in data/Missions/_gen.Mission: the displayed
        skill - the raw nibble plus one - capped at 4, one lower for a man
        who is hurt. Two things follow. Skills 4 and skills 5 fly
        identically, so a fifth point buys nothing in the air; and a wound
        costs a whole level. The wound penalty rests on a single observation
        (a pilot in hospital on 60 health), so treat it as likely, not proven.
        """
        ai = min(4, skills + 1)
        if state == 4 or health < 100:
            ai = max(0, ai - 1)
        return ai

    RESERVE_TOP = 5000                   # at or above this a man is dead, not benched

    def _read_man(self, row, tail: str, slot: int) -> Dict:
        """One pilot, with the numbers the board ranks him on."""
        def nib(value, index):
            return (int(value or 0) >> (4 * index)) & 15

        pers, lead = row["persLevel"], row["leadLevel"]
        first = (row["name"] or "").strip()
        man = {
            "id": row["id"],
            "who": f"{first} {row['lastName']}".strip(),
            "short": f"{first[:1]}. {row['lastName']}" if first else row["lastName"],
            "sk": nib(pers, 0), "co": nib(pers, 1), "di": nib(pers, 2),
            # boosters in the panel's own order, which is how the mission
            # screen prints the commander's three chips
            "boost": (nib(lead, 0), nib(lead, 2), nib(lead, 1)),
            "health": int(row["health"] or 100),
            "state": int(row["state"] or 0),
            "player": bool(row["isPlayer"]),
            "sorties": int(row["sorties"] or 0),
            "home": slot,
            "tail": tail,
        }
        man["ai"] = self.ai_level(man["sk"], man["health"], man["state"])
        man["hurt"] = man["state"] == 4 or man["health"] < 100
        # state 0 is the only one that means "can fly today". 1 is a man
        # walking home after going down - unhurt, due back at stateEndDate,
        # and the Combat Units screen greys him out with a clock. 2 and 3 are
        # the dead and the missing, 4 is hospital. Anything but 0 is a man the
        # squadron cannot count on, so none of them is ever brought up.
        man["available"] = man["state"] == 0
        return man

    def seats(self) -> int:
        """
        How many seats this squadron's line-up has, read from its own data.

        Not a constant, because the establishments differ. An American
        squadron is 24 seats in six flights of four; an eastern regiment is
        a commander pair and three squadrons of twelve, 38 in all.

        Most eastern careers show the upper seats empty. A mature 48/48
        regiment was found holding 24 men in seats 0-23 with seven fit
        pilots benched, which suggests the game keeps a target strength
        rather than filling the establishment - but that is inference from
        one career, not something proven.

        What *is* proven is that the seats exist: assigning men into the 3rd
        Squadron in game wrote slots 26, 27 and 28, exactly where this
        mapping puts it.

        Rather than encode either establishment, or trust squadrons.cfg
        (whose pilotsCap of 48 matches neither seat count), the chart takes
        the highest seat the career actually uses and rounds up to a whole
        flight. It grows with the unit and never invents a seat the game
        has not made.

        Rounded to its own establishment, not to a flat four: an eastern
        regiment is a commander pair and squadrons of twelve, so its seat
        count is 2 + 12n and never 40. Floored at the full establishment -
        24 in the west, 38 in the east - so a fresh career shows the empty
        seats the game shows, including an empty 3rd Squadron.
        """
        with self._open() as con:
            hi = con.execute(
                """SELECT max(slot) FROM (
                       SELECT slot FROM pilot WHERE isDeleted=0 AND slot<?
                       UNION ALL
                       SELECT slot FROM plane WHERE isDeleted=0 AND slot<?)""",
                (self.BENCH_BASE, self.BENCH_BASE)).fetchone()[0]
            row = con.execute(
                "SELECT country FROM pilot WHERE id=(SELECT playerId FROM career)"
            ).fetchone()
        country = row[0] if row else 601
        used = 0 if hi is None else hi + 1
        if country in (501, 502, 503):
            return max(self.EAST_SEATS, 2 + 12 * -(-max(0, used - 2) // 12))
        return max(self.SEATS, -(-used // 4) * 4)

    def country(self) -> int:
        """The air force this career belongs to, which chooses the shape."""
        with self._open() as con:
            row = con.execute(
                "SELECT country FROM pilot WHERE id=(SELECT playerId FROM career)"
            ).fetchone()
        return row[0] if row else 601

    def player_portrait(self) -> Dict[str, Any]:
        """The current player only, including the path the game renders."""
        with self._open() as con:
            row = con.execute(
                """SELECT id, name, lastName, personageId, avatarPath
                   FROM pilot WHERE id=(SELECT playerId FROM career)"""
            ).fetchone()
        if row is None:
            raise ValueError("the career has no current player")
        return {
            "id": row["id"],
            "name": f"{row['name']} {row['lastName']}".strip(),
            "personage_id": row["personageId"],
            "avatar_path": row["avatarPath"] or "",
        }

    def player_biography(self) -> Dict[str, Any]:
        """The current player's chosen biography, as ``pilot.description`` holds it."""
        with self._open() as con:
            row = con.execute(
                """SELECT id, name, lastName, country, description, leadLevel
                   FROM pilot WHERE id=(SELECT playerId FROM career)"""
            ).fetchone()
        if row is None:
            raise ValueError("the career has no current player")
        fields = {}
        for pair in urllib.parse.unquote(row["description"] or "").split("&"):
            key, _, value = pair.partition("=")
            if key:
                fields[key] = value
        return {
            "id": row["id"],
            "name": f"{row['name']} {row['lastName']}".strip(),
            "country": row["country"],
            "description": row["description"] or "",
            "biography_id": fields.get("biographyId", ""),
            "lead_level": row["leadLevel"] or 0,
        }

    def set_player_boosters(self, expected: int, lead_level: int) -> Path:
        """
        Write the player's ``leadLevel`` (his boosters), after backup - only
        if it still holds ``expected``, the value the tab was showing.
        """
        backup = self.backup()
        with self._open(write=True) as con:
            con.execute("BEGIN IMMEDIATE")
            changed = con.execute(
                """UPDATE pilot SET leadLevel=?
                   WHERE id=(SELECT playerId FROM career) AND leadLevel=?""",
                (int(lead_level), int(expected)),
            ).rowcount
            if changed != 1:
                raise ValueError("the boosters changed in the meantime - refresh and try again")
            con.commit()
        return backup

    def set_player_portrait(self, avatar_path: str) -> Path:
        """Point the current player's portrait at a loose DDS, after backup."""
        from korea_service_record.portraitfix import MAX_AVATAR_PATH
        if len(avatar_path) > MAX_AVATAR_PATH:
            # The game aborts at the next new day on a longer path.
            raise ValueError(f"portrait path longer than {MAX_AVATAR_PATH} characters: {avatar_path}")
        backup = self.backup()
        with self._open(write=True) as con:
            con.execute("BEGIN IMMEDIATE")
            changed = con.execute(
                "UPDATE pilot SET avatarPath=? WHERE id=(SELECT playerId FROM career)",
                (avatar_path,),
            ).rowcount
            if changed != 1:
                raise ValueError("the career has no current player")
            con.commit()
        return backup

    PILOT_COLS = """SELECT id, slot, name, lastName, persLevel, leadLevel,
                           health, state, isPlayer, sorties FROM pilot
                    WHERE isDeleted=0"""

    def pool_pilots(self) -> List[Dict]:
        """
        The bench: everyone not in the line-up and not dead.

        Two bands sit here. 2000 and up is the replacement pool proper, a
        queue that appends on the way in and closes up on the way out. 1000
        and up is a man whose aircraft is in repair, which the Combat Units
        screen calls "in reserve - NOT READY"; the game also walks a pilot
        through that band as a staging step while a move commits. Neither has
        an aircraft of his own, so no tail number is shown.
        """
        count = self.seats()
        with self._open() as con:
            rows = con.execute(
                f"{self.PILOT_COLS} AND slot>=? AND slot<? ORDER BY slot",
                (count, self.RESERVE_TOP)).fetchall()
        return [self._read_man(r, "", r["slot"]) for r in rows]

    def flight_seats(self) -> List[Dict]:
        """Every seat in order, each with its pilot and aircraft or None."""
        count = self.seats()
        with self._open() as con:
            men = {r["slot"]: r for r in con.execute(
                f"{self.PILOT_COLS} AND slot<?", (count,))}
            planes = {r["slot"]: r for r in con.execute(
                "SELECT id, slot, tcode, state FROM plane WHERE isDeleted=0 AND slot<?",
                (count,))}
            row = con.execute("SELECT watchmen FROM squadron").fetchone()
        alert = self.parse_watchmen(row[0] if row else "")
        blocks = line_up_blocks(self.country(), count)
        seats = []
        for slot in range(count):
            block, pos = seat_position(blocks, slot)
            row, air = men.get(slot), planes.get(slot)
            man = None
            if row is not None:
                man = self._read_man(
                    row, decode_tcode(air["tcode"]) if air is not None else "", slot)
            seats.append({"slot": slot, "flight": block, "section": pos // 2,
                          # A lead is the first seat of its own block, and a
                          # section lead the first of its pair within it.
                          "lead": pos == 0, "sec_lead": pos % 2 == 0,
                          "alert": slot in alert, "pilot": man,
                          "plane_state": air["state"] if air is not None else None})
        return seats

    def reseat(self, plan: Dict[int, int]) -> Path:
        """
        Rewrite the line-up. ``plan`` maps seat -> pilot id, and a pilot may
        come from the bench: anyone seated now but absent from the plan is
        sent down to the pool.

        The exchange must be **one for one** - as many men seated after as
        before. That is what keeps the aircraft safe. Your own history shows a
        promotion drawing a spare airframe from plane slot 2000 and a
        demotion sending one back, but with the count held equal no aircraft
        ever crosses that boundary: a man moving inside the line-up carries
        his own, and a seat taken by someone off the bench keeps the aeroplane
        the outgoing man left in it. Nothing can be stranded in a slot the
        game does not read.

        Men sent down are appended to the end of the pool, and the pool is
        renumbered from 2000 with no gaps, which is what the game does.
        Returns the backup path.
        """
        count = self.seats()
        backup = self.backup()
        with self._open(write=True) as con:
            con.execute("BEGIN IMMEDIATE")
            seated = {r["slot"]: r["id"] for r in con.execute(
                "SELECT id, slot FROM pilot WHERE isDeleted=0 AND slot<?", (count,))}
            benched = [r["id"] for r in con.execute(
                """SELECT id FROM pilot WHERE isDeleted=0 AND slot>=? AND slot<?
                   ORDER BY slot""", (count, self.RESERVE_TOP))]
            # the 2000 band is the queue that renumbers; the 1000 band means
            # a man whose aircraft is in repair and is left exactly where it
            # is, or a promotion would quietly change what his status says
            pool_now = [r["id"] for r in con.execute(
                """SELECT id FROM pilot WHERE isDeleted=0 AND slot>=? AND slot<?
                   ORDER BY slot""", (RESERVE_BASE, self.RESERVE_TOP))]
            known = set(seated.values()) | set(benched)
            if len(set(plan.values())) != len(plan):
                raise ValueError("two seats want the same pilot")
            if not set(plan.values()) <= known:
                raise ValueError("the plan names a pilot who is neither seated nor benched")
            if len(plan) != len(seated):
                raise ValueError("the exchange must be one for one")

            planes = {r["slot"]: r["id"] for r in con.execute(
                "SELECT id, slot FROM plane WHERE isDeleted=0 AND slot<?", (count,))}
            home = {pid: slot for slot, pid in seated.items()}
            promoted = [pid for pid in plan.values() if pid not in home]
            demoted = [pid for pid in seated.values() if pid not in set(plan.values())]
            pilot_home = {r["id"]: r["slot"] for r in con.execute(
                """SELECT id, slot FROM pilot WHERE isDeleted=0
                   AND slot>=? AND slot<?""", (count, self.RESERVE_TOP))}

            # park the line-up out of range: writing a seat that its new
            # occupant has not yet vacated would put two men in one aeroplane
            for n, pid in enumerate(seated.values()):
                con.execute("UPDATE pilot SET slot=? WHERE id=?", (self.PARK + n, pid))
            for n, aid in enumerate(planes.values()):
                con.execute("UPDATE plane SET slot=? WHERE id=?", (self.PARK + n, aid))

            # A man promoted out of the repair band leaves the aeroplane that
            # was being mended for him. The game sends it to the plane pool -
            # log 31 of this career did exactly that, Heinecke 1003 -> seat 14
            # with his old airframe going to plane slot 2000 - so it is put on
            # the end of that queue rather than left in a band nobody reads.
            repair = {r["slot"]: r["id"] for r in con.execute(
                """SELECT id, slot FROM plane WHERE isDeleted=0
                   AND slot>=1000 AND slot<?""", (RESERVE_BASE,))}
            plane_pool = [r["id"] for r in con.execute(
                """SELECT id FROM plane WHERE isDeleted=0 AND slot>=? AND slot<?
                   ORDER BY slot""", (RESERVE_BASE, self.RESERVE_TOP))]
            grounded = [repair[s] for pid in promoted
                        for s in (pilot_home.get(pid),) if s in repair]

            # aircraft the demoted men leave behind, for the men coming up
            spare = [planes[home[pid]] for pid in demoted if home[pid] in planes]
            for slot, pid in plan.items():
                con.execute("UPDATE pilot SET slot=? WHERE id=?", (slot, pid))
                if pid in home:
                    aid = planes.get(home[pid])
                elif spare:
                    aid = spare.pop(0)
                else:
                    aid = None
                if aid is not None:
                    con.execute("UPDATE plane SET slot=? WHERE id=?", (slot, aid))

            # the pool: those who were in it, less anyone promoted, plus the
            # men just sent down - then renumbered from 2000 without gaps
            bench = [pid for pid in pool_now if pid not in promoted] + demoted
            for n, pid in enumerate(bench):
                con.execute("UPDATE pilot SET slot=? WHERE id=?", (self.PARK + 100 + n, pid))
            for n, pid in enumerate(bench):
                con.execute("UPDATE pilot SET slot=? WHERE id=?", (RESERVE_BASE + n, pid))

            # and the airframes left mending behind a promoted man join the
            # plane pool, renumbered from 2000 like the men's queue
            if grounded:
                for n, aid in enumerate(plane_pool + grounded):
                    con.execute("UPDATE plane SET slot=? WHERE id=?",
                                (self.PARK + 200 + n, aid))
                for n, aid in enumerate(plane_pool + grounded):
                    con.execute("UPDATE plane SET slot=? WHERE id=?",
                                (RESERVE_BASE + n, aid))
            con.commit()
        return backup

    # -- writes ------------------------------------------------------------

    def backup(self) -> Path:
        return corrections.backup(self.path)

    @staticmethod
    def _free_slot(con: sqlite3.Connection, pilot_id: Optional[int] = None) -> int:
        """
        Lowest free line-up slot, else the lowest free reserve slot.

        A pilot being revived does not count as blocking himself, so he
        keeps his own place when it is still a line-up slot and nobody has
        moved into it. Once the day has turned the game has filed him among
        the lost - slot 5000 and up - and then he takes the lowest free
        place like anybody else.
        """
        taken = {r[1] for r in con.execute("SELECT id, slot FROM pilot WHERE isDeleted=0")
                 if pilot_id is None or r[0] != pilot_id}
        if pilot_id is not None:
            mine = con.execute("SELECT slot FROM pilot WHERE id=?", (pilot_id,)).fetchone()
            if mine is not None and mine[0] in LINEUP and mine[0] not in taken:
                return mine[0]
        for slot in LINEUP:
            if slot not in taken:
                return slot
        slot = RESERVE_BASE
        while slot in taken:
            slot += 1
        return slot

    def revive(self, pilot_id: int, restore_plane: bool) -> Path:
        """
        Undo a death or disappearance. Raises sqlite3.OperationalError when the
        game holds the file. Returns the backup path.
        """
        backup = self.backup()
        with self._open(write=True) as con:
            con.execute("BEGIN IMMEDIATE")          # fails at once if locked
            pilot = con.execute("SELECT * FROM pilot WHERE id=?", (pilot_id,)).fetchone()
            if pilot is None or pilot["state"] not in (2, 3):
                raise ValueError("not a lost pilot")
            sortie = con.execute(
                "SELECT * FROM sortie WHERE pilotId=? AND status IN (2, 3) ORDER BY id DESC LIMIT 1",
                (pilot_id,)).fetchone()
            slot = self._free_slot(con, pilot_id)
            con.execute("UPDATE pilot SET state=0, health=100, slot=? WHERE id=?", (slot, pilot_id))
            # The KIA/MIA event of that loss. Retired, not deleted: the game
            # never reads deleted rows, and the row stays for the record.
            con.execute(
                "UPDATE event SET isDeleted=1 WHERE pilotId=? AND type IN (3, 4) AND isDeleted=0 "
                "AND substr(date, 1, 10)=?", (pilot_id, (pilot["stateDate"] or "")[:10]))
            # Reviving the player is not finished with the pilot row. The
            # game decides whether to offer postpone / end career / assign a
            # new commander from the CAREER row, so a revived commander is
            # still gone as far as that screen is concerned: it reads
            # state=1 and a resumeDate in the future - the day the squadron
            # was to change hands. A healthy career is state=0 with no
            # resumeDate. Harmless for an AI pilot, who is never the reason
            # that flag was set.
            career = con.execute("SELECT playerId, state FROM career").fetchone()
            if career is not None and career["playerId"] == pilot_id and career["state"]:
                con.execute("UPDATE career SET state=0, resumeDate='0000.00.00'")

            if sortie is not None:
                if restore_plane:
                    con.execute("UPDATE sortie SET status=0, health=100, planeStatus=0, planeHealth=100 "
                                "WHERE id=?", (sortie["id"],))
                    plane = con.execute("SELECT * FROM plane WHERE id=?", (sortie["planeId"],)).fetchone()
                    if plane is not None and plane["state"] == 3:
                        taken = {r[0] for r in con.execute("SELECT slot FROM plane WHERE isDeleted=0")}
                        pslot = next((s for s in LINEUP if s not in taken), RESERVE_BASE)
                        con.execute("UPDATE plane SET state=0, health=100, slot=? WHERE id=?",
                                    (pslot, plane["id"]))
                    con.execute(
                        "UPDATE event SET isDeleted=1 WHERE pilotId=? AND type=2 AND isDeleted=0 "
                        "AND missionId=?", (pilot_id, sortie["missionId"]))
                else:
                    # Bailed out: he is back, the aircraft is not.
                    con.execute("UPDATE sortie SET status=0, health=100 WHERE id=?", (sortie["id"],))
            con.commit()
        return backup

    def capture(self, sortie_id: int) -> Path:
        """
        Mark the pilot of that sortie captured, the way the game books an AI
        pilot lost over enemy territory: state 3 from the moment he went
        down, the sortie's fate 3 and one MIA event. The game does the rest
        (for the player: "Commander Captured" on the next day). Returns the
        backup path; raises sqlite3.OperationalError when the game holds the file.
        """
        backup = self.backup()
        with self._open(write=True) as con:
            con.execute("BEGIN IMMEDIATE")
            sortie = con.execute("SELECT * FROM sortie WHERE id=?", (sortie_id,)).fetchone()
            if sortie is None or sortie["status"] in (2, 3):
                raise ValueError("not a survivable loss")
            pilot = con.execute("SELECT * FROM pilot WHERE id=?", (sortie["pilotId"],)).fetchone()
            if pilot is None or pilot["state"] not in (0, 1):
                raise ValueError("pilot not on the roll")
            # The moment he went down: his shoot-down event on that mission,
            # else the mission's end.
            hit = con.execute(
                "SELECT date FROM event WHERE type=2 AND pilotId=? AND missionId=? AND isDeleted=0 "
                "ORDER BY id DESC LIMIT 1", (pilot["id"], sortie["missionId"])).fetchone()
            mission = con.execute("SELECT endTime FROM mission WHERE id=?", (sortie["missionId"],)).fetchone()
            when = (hit["date"] if hit else None) or (mission["endTime"] if mission else None) or sortie["date"]
            con.execute("UPDATE pilot SET state=3, stateDate=?, stateEndDate='0000.00.00 00:00:00' WHERE id=?",
                        (when, pilot["id"]))
            con.execute("UPDATE sortie SET status=3 WHERE id=?", (sortie_id,))
            con.execute(
                """INSERT INTO event (date, type, pilotId, rankId, missionId, squadronId, careerId, planeId,
                                      ipar1, ipar2, ipar3, ipar4, tpar1, tpar2, tpar3, tpar4, insdate, isDeleted)
                   VALUES (?, 4, ?, 0, ?, ?, ?, -1, -1, -1, -1, -1, '', '', '', '', ?, 0)""",
                (when, pilot["id"], sortie["missionId"], pilot["squadronId"],
                 con.execute("SELECT id FROM career").fetchone()[0],
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            con.commit()
        return backup

    def add_points(self, amount: int) -> Path:
        backup = self.backup()
        with self._open(write=True) as con:
            con.execute("BEGIN IMMEDIATE")
            con.execute("UPDATE squadron SET awardPoints = awardPoints + ?", (amount,))
            con.commit()
        return backup


def list_careers(game: Path) -> List[Career]:
    folder = game / "data" / "Career"
    if not folder.is_dir():
        return []
    return [Career(p) for p in sorted(folder.glob("*.db"))]


# ---------------------------------------------------------------------------
# The window
# ---------------------------------------------------------------------------

def decode_tcode(code: str) -> str:
    """
    The tail number a ``plane.tcode`` stands for, e.g. FF-117.

    The field is URL-encoded and then shifted: the character '!' is the digit
    zero, so '%22%22%28' reads 1, 1, 7. The first three characters are the
    unit prefix and are dropped.
    """
    if not code:
        return ""
    try:
        raw = urllib.parse.unquote(code)
    except Exception:
        return ""
    digits = "".join(str(ord(ch) - 0x21) for ch in raw[3:] if 0x21 <= ord(ch) <= 0x2A)
    return f"FF-{digits}" if digits else ""


def propose_seating(seats: List[Dict], bench: Optional[List[Dict]] = None) -> Dict[int, int]:
    """
    A seating to accept or argue with, built on what the game actually reads.

    Exactly one man's boosters count for a mission: the commander's, and they
    cover every aircraft in the force. The commander is whoever holds the
    **lowest-numbered seat that flies** - which matches all four observed
    cases (flights 2-4 gave Mull at 4, 1-4 gave the player at 0, 3-4 gave Galt
    at 8, flight 4 alone gave Winicki at 12) and also covers sending a single
    section, where the section lead takes it.

    So there is no one seat to manage. Any flight may be the lowest one sent,
    and so may any section, which means **every lead seat should carry
    boosters**: flight leads first, section leads next, each ranked on the sum
    of their three boosters and then on skill. Because seats fill in slot
    order within a tier, the best-boostered man lands in the lowest lead seat,
    which is the one most often in command.

    Given a bench, men from the reserve compete for the seats on the same
    terms, one for one: whoever is displaced goes down to the pool. Only a man
    in state 0 is ever brought up - not the wounded, and not one still walking
    home from a sortie he did not come back from, however well he flies.
    Someone already seated who has gone unavailable keeps his seat, since the
    game keeps him there too and he is usually back within a day, but he is
    passed over for the lead and alert seats.

    Wingmen are seated on what the game reads for them instead: AILevel, which
    comes from skill alone and saturates at 4, then discipline, then rest.
    Filling a tier at a time spreads strength across the flights rather than
    piling it into the first, because missions go out as whole flights. The
    alert seats take no wounded or absent man while a fit one is left, since
    they are the ones that scramble without warning - and which seats those
    are is read from squadron.watchmen, because the player can move the D
    flight anywhere.

    One floor applies. Nobody below LEAD_MIN_AI leads a flight or a section
    while a qualified man is free, because boosters are so scarce - nought to
    three across a whole squadron - that ranking on them alone otherwise hands
    a flight to the worst flier in it, and, once the reserve is in play, hands
    a section to a replacement who has never flown.
    """
    taken = [s for s in seats if s["pilot"]]
    # A benched man is only ever picked when he is strictly better, because
    # the "is he already here" tiebreak can never fire for him - his home is a
    # pool slot, never a seat. So the line-up is left alone unless the reserve
    # genuinely improves it.
    pool = [s["pilot"] for s in taken] + [
        m for m in (bench or []) if m["available"]]
    plan = {}

    player = next((m for m in pool if m["player"]), None)
    if player is not None:                       # the commander keeps his seat
        plan[player["home"]] = player["id"]
        pool.remove(player)

    # Flight leads first, then section leads, then the rest - read off the
    # seat itself, because which numbers those are depends on the shape.
    rank_of = {s["slot"]: (0 if s["lead"] else 1 if s.get("sec_lead") else 2)
               for s in taken}
    lead_seat = {s["slot"]: bool(s.get("sec_lead")) for s in taken}
    open_seats = [s["slot"] for s in taken if s["slot"] not in plan]
    open_seats.sort(key=lambda s: (rank_of.get(s, 2), s))

    # The trailing "is he already here" term leaves a man where he sits when
    # nothing else separates him from the alternative: a proposal you have to
    # undo by hand is worse than no proposal at all.
    def as_lead(man, slot):
        return (sum(man["boost"]), man["ai"], man["sk"], man["home"] == slot)

    def as_wingman(man, slot):
        return (man["ai"], man["di"], man["sk"], man["home"] == slot)

    alert = {s["slot"] for s in taken if s.get("alert")}
    for slot in open_seats:
        if not pool:
            break
        take = pool
        if slot in alert:                        # scrambles without warning
            take = [m for m in take if m["available"] and not m["hurt"]] or pool
        if lead_seat.get(slot):                  # a flight or section lead
            here = [m for m in take if m["available"]]
            take = [m for m in (here or take)
                    if m["ai"] >= Career.LEAD_MIN_AI] or here or take
        rank = as_lead if lead_seat.get(slot) else as_wingman
        pick = max(take, key=lambda m: rank(m, slot))
        plan[slot] = pick["id"]
        pool.remove(pick)
    return plan


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        lang = pick_language()
        self.lang = lang
        self.t = STRINGS[lang]
        # The game's own names for the parts of a line-up, so the board and
        # the Combat Units screen agree. Read once; {} if it cannot be, and
        # every use falls back to our own string.
        self.game_t = game_labels(lang)
        self.title(self.t["title"])
        # wide enough for the Flights board - six columns of cards - without
        # the reader having to stretch the window before it is any use
        self.geometry("1140x960")
        self.minsize(940, 700)
        self._skin()
        self.careers: List[Career] = []
        self.career: Optional[Career] = None
        self.lost: List[Dict] = []
        self._build()
        self._load_careers()

    # -- looks ---------------------------------------------------------------

    # The Service Record's own palette, so the two windows read as one
    # product rather than an application and its utility. ttk on Windows
    # defaults to a theme that ignores most colour settings; clam honours
    # them, which is the only reason it is chosen here.
    PAPER, PANEL, DESK = "#fbf6e9", "#f8f2e0", "#ece1c8"
    INK, INK_MUTED, ACCENT = "#2c2212", "#4a3a24", "#8b6f4a"
    ACCENT_DARK, BORDER, BAD = "#5a4022", "#cbb999", "#8c3a2c"
    STRIPE = "#f3ebd8"                  # every other row, a shade off the paper
    DUTY = "#4a6b8a"                    # the alert seats, as the game outlines them

    def _skin(self) -> None:
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except tk.TclError:              # a stripped Tk: leave it grey but working
            return
        self.configure(background=self.DESK)
        head = ("Georgia", 10, "bold")
        st.configure(".", background=self.PANEL, foreground=self.INK,
                     fieldbackground=self.PAPER, bordercolor=self.BORDER,
                     lightcolor=self.PANEL, darkcolor=self.PANEL, focuscolor=self.ACCENT)
        st.configure("TFrame", background=self.PANEL)
        st.configure("TLabel", background=self.PANEL, foreground=self.INK)
        st.configure("TLabelframe", background=self.PANEL, bordercolor=self.BORDER)
        st.configure("TLabelframe.Label", background=self.PANEL, foreground=self.ACCENT_DARK,
                     font=head)
        st.configure("TSeparator", background=self.BORDER)
        st.configure("TNotebook", background=self.DESK, bordercolor=self.BORDER, tabmargins=(6, 4, 6, 0))
        st.configure("TNotebook.Tab", background=self.DESK, foreground=self.INK_MUTED,
                     padding=(14, 6), font=head)
        st.map("TNotebook.Tab",
               background=[("selected", self.PANEL)],
               foreground=[("selected", self.ACCENT_DARK)],
               expand=[("selected", (0, 0, 0, 2))])
        st.configure("TButton", background=self.PAPER, foreground=self.INK,
                     bordercolor=self.BORDER, padding=(10, 4), relief="flat")
        st.map("TButton",
               background=[("pressed", self.ACCENT), ("active", "#f0e6cf"), ("disabled", self.DESK)],
               foreground=[("pressed", self.PAPER), ("disabled", "#9c8f79")],
               bordercolor=[("active", self.ACCENT)])
        for widget in ("TEntry", "TCombobox", "TSpinbox"):
            st.configure(widget, fieldbackground=self.PAPER, background=self.PAPER,
                         foreground=self.INK, bordercolor=self.BORDER, arrowcolor=self.ACCENT_DARK,
                         insertcolor=self.INK)
        st.map("TCombobox", fieldbackground=[("readonly", self.PAPER)],
               selectbackground=[("readonly", self.PAPER)],
               selectforeground=[("readonly", self.INK)])
        st.configure("Treeview", background=self.PAPER, fieldbackground=self.PAPER,
                     foreground=self.INK, bordercolor=self.BORDER, rowheight=23)
        st.configure("Treeview.Heading", background=self.DESK, foreground=self.ACCENT_DARK,
                     relief="flat", font=head, padding=(6, 4))
        st.map("Treeview.Heading", background=[("active", "#e2d5b8")])
        st.map("Treeview", background=[("selected", self.ACCENT)],
               foreground=[("selected", self.PAPER)])
        st.configure("TCheckbutton", background=self.PANEL)
        st.configure("Horizontal.TProgressbar", background=self.ACCENT, troughcolor=self.PAPER)

    # -- layout --------------------------------------------------------------

    def _build(self) -> None:
        pad = {"padx": 10, "pady": 6}
        band = tk.Frame(self, background=self.ACCENT_DARK, height=3)
        band.pack(fill="x", side="top")
        head = tk.Frame(self, background=self.PANEL)
        head.pack(fill="x", side="top")
        tk.Label(head, text=self.t["title"], background=self.PANEL, foreground=self.ACCENT_DARK,
                 font=("Georgia", 15), anchor="w").pack(fill="x", padx=12, pady=(10, 2))
        tk.Label(head, text=self.t["subtitle"], background=self.PANEL, foreground="#6b5a3f",
                 font=("Georgia", 9), anchor="w").pack(fill="x", padx=12, pady=(0, 8))
        ttk.Separator(self).pack(fill="x")
        top = ttk.Frame(self)
        top.pack(fill="x", **pad)
        ttk.Label(top, text=self.t["career"]).pack(side="left")
        self.career_var = tk.StringVar()
        self.career_box = ttk.Combobox(top, textvariable=self.career_var, state="readonly", width=60)
        self.career_box.pack(side="left", padx=8, fill="x", expand=True)
        self.career_box.bind("<<ComboboxSelected>>", lambda _e: self._select_career())
        ttk.Button(top, text=self.t["refresh"], command=self._refresh).pack(side="left")

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, **pad)

        # -- revive tab
        rev = ttk.Frame(nb)
        nb.add(rev, text=self.t["tab_revive"])
        self.rule_var = tk.StringVar()
        ttk.Label(rev, textvariable=self.rule_var, wraplength=700).pack(anchor="w", padx=8, pady=(8, 2))
        ttk.Label(rev, text=self.t["player_note"], wraplength=700,
                  foreground="#666").pack(anchor="w", padx=8, pady=(0, 6))
        cols = ("name", "state", "date", "can")
        self.tree = ttk.Treeview(rev, columns=cols, show="headings", height=8, selectmode="browse")
        self.tree.tag_configure("odd", background=self.STRIPE)
        for key, width in (("name", 260), ("state", 160), ("date", 110), ("can", 200)):
            self.tree.heading(key, text=self.t["col_" + key], anchor="w")
            self.tree.column(key, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=8)
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._update_buttons())
        bottom = ttk.Frame(rev)
        bottom.pack(fill="x", padx=8, pady=8)
        self.plane_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(bottom, text=self.t["restore_plane"], variable=self.plane_var).pack(side="left")
        self.revive_btn = ttk.Button(bottom, text=self.t["revive"], command=self._revive, state="disabled")
        self.revive_btn.pack(side="right")

        # -- captured tab
        cap = ttk.Frame(nb)
        nb.add(cap, text=self.t["tab_captured"])
        ttk.Label(cap, text=self.t["captured_intro"], wraplength=700).pack(anchor="w", padx=8, pady=(8, 6))
        cols = ("name", "sortie", "fate", "can2")
        self.cap_tree = ttk.Treeview(cap, columns=cols, show="headings", height=8, selectmode="browse")
        self.cap_tree.tag_configure("odd", background=self.STRIPE)
        for key, width in (("name", 220), ("sortie", 110), ("fate", 240), ("can2", 170)):
            self.cap_tree.heading(key, text=self.t["col_" + key], anchor="w")
            self.cap_tree.column(key, width=width, anchor="w")
        self.cap_tree.pack(fill="both", expand=True, padx=8)
        self.cap_tree.bind("<<TreeviewSelect>>", lambda _e: self._update_buttons())
        capb = ttk.Frame(cap)
        capb.pack(fill="x", padx=8, pady=8)
        self.capture_btn = ttk.Button(capb, text=self.t["capture"], command=self._capture, state="disabled")
        self.capture_btn.pack(side="right")

        # -- flight time tab
        ft = ttk.Frame(nb)
        nb.add(ft, text=self.t["tab_times"])
        ttk.Label(ft, text=self.t["times_intro"], wraplength=700).pack(anchor="w", padx=8, pady=(8, 6))
        cols = ("mission", "flown", "planned", "source", "applied")
        self.ft_tree = ttk.Treeview(ft, columns=cols, show="headings", height=7, selectmode="extended")
        self.ft_tree.tag_configure("odd", background=self.STRIPE)
        for key, width in (("mission", 200), ("flown", 90), ("planned", 90), ("source", 130), ("applied", 130)):
            self.ft_tree.heading(key, text=self.t["col_" + key], anchor="w")
            self.ft_tree.column(key, width=width, anchor="w")
        self.ft_tree.pack(fill="both", expand=True, padx=8)
        self.auto_label = ttk.Label(ft, text="", wraplength=700)
        self.auto_label.pack(anchor="w", padx=8, pady=(6, 0))
        ftb = ttk.Frame(ft)
        ftb.pack(fill="x", padx=8, pady=6)
        ttk.Button(ftb, text=self.t["compute"], command=self._compute_times).pack(side="left")
        ttk.Button(ftb, text=self.t["apply"], command=self._apply_hours).pack(side="right")
        ttk.Button(ftb, text=self.t["restore"], command=self._restore_hours).pack(side="right", padx=8)
        self.aw_frame = ttk.Frame(ft)
        self.aw_frame.pack(fill="x", padx=8, pady=(0, 6))

        # -- points tab
        pts = ttk.Frame(nb)
        nb.add(pts, text=self.t["tab_points"])
        self.points_var = tk.StringVar()
        ttk.Label(pts, textvariable=self.points_var, font=("", 11)).pack(anchor="w", padx=8, pady=(16, 8))
        row = ttk.Frame(pts)
        row.pack(anchor="w", padx=8)
        self.amount = tk.IntVar(value=5)
        ttk.Spinbox(row, from_=1, to=500, textvariable=self.amount, width=6).pack(side="left")
        ttk.Button(row, text=self.t["points_add"], command=self._add_points).pack(side="left", padx=8)

        # -- pending awards, on the same tab: they are what the points buy
        ttk.Separator(pts).pack(fill="x", padx=8, pady=(14, 8))
        ttk.Label(pts, text=self.t["pending_intro"], wraplength=720,
                  foreground="#444").pack(anchor="w", padx=8)
        # Three attributes, each as a pair: what the man had before the
        # awards were presented and what he has after. Boosters are not
        # shown - a decoration never moves them, only a promotion does.
        self.pend_tree = ttk.Treeview(
            pts, columns=("who", "status", "award", "earned",
                          "sk0", "sk1", "di0", "di1", "co0", "co1"),
            show="headings", height=9, selectmode="none")
        # The fallen are listed but stand out: a posthumous award is the
        # commander's decision, not something to tick past by accident.
        self.pend_tree.tag_configure("gone", foreground=self.BAD)
        self.pend_tree.tag_configure("odd", background=self.STRIPE)
        for col, w in (("who", 170), ("status", 100), ("award", 300), ("earned", 100)):
            self.pend_tree.heading(col, text=self.t["pend_col_" + col], anchor="w")
            self.pend_tree.column(col, width=w, anchor="w")
        # The pairs are narrow and centred: the eye compares them down the
        # column, and the "after" heading repeats so each pair reads as one.
        for col, head in (("sk0", "pend_col_sk"), ("sk1", "pend_col_after"),
                          ("di0", "pend_col_di"), ("di1", "pend_col_after"),
                          ("co0", "pend_col_co"), ("co1", "pend_col_after")):
            self.pend_tree.heading(col, text=self.t[head], anchor="center")
            self.pend_tree.column(col, width=58 if col.endswith("0") else 48,
                                  anchor="center", stretch=False)
        # A value that went up is worth seeing at a glance.
        self.pend_tree.tag_configure("bumped", foreground=self.ACCENT_DARK)
        self.pend_tree.pack(fill="both", expand=True, padx=8, pady=(6, 4))
        # A checkbox per row would need a third-party widget; a tick in the
        # first column and a click to toggle does the same job with ttk alone.
        self.pend_tree.bind("<Button-1>", self._toggle_pending)
        self.pend_checked = set()
        self.pending = []          # filled on the first refresh
        prow = ttk.Frame(pts)
        prow.pack(anchor="w", padx=8, pady=(0, 10))
        ttk.Button(prow, text=self.t["pend_all"],
                   command=lambda: self._check_pending(True)).pack(side="left")
        ttk.Button(prow, text=self.t["pend_none"],
                   command=lambda: self._check_pending(False)).pack(side="left", padx=8)
        self.pend_btn = ttk.Button(prow, text=self.t["pend_grant"], command=self._grant_pending)
        self.pend_btn.pack(side="left", padx=8)
        self.pend_var = tk.StringVar()
        ttk.Label(prow, textvariable=self.pend_var).pack(side="left", padx=8)

        # -- custom pilot photo tab
        photo = ttk.Frame(nb)
        nb.add(photo, text=self.t["tab_photo"])
        ttk.Label(photo, text=self.t["photo_intro"], wraplength=1080,
                  foreground="#444").pack(anchor="w", padx=8, pady=(8, 6))
        photo_body = ttk.Frame(photo)
        photo_body.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.photo_canvas = tk.Canvas(
            photo_body, width=pilot_photo.PORTRAIT_SIZE,
            height=pilot_photo.PORTRAIT_SIZE, highlightthickness=1,
            highlightbackground=self.BORDER, background=self.PAPER,
        )
        self.photo_canvas.pack(side="left", anchor="n")
        self.photo_canvas.bind("<ButtonPress-1>", self._photo_drag_start)
        self.photo_canvas.bind("<B1-Motion>", self._photo_drag_move)

        photo_controls = ttk.Frame(photo_body)
        photo_controls.pack(side="left", fill="both", expand=True, padx=(18, 4))
        self.photo_current_var = tk.StringVar(value=self.t["photo_current"].format(path="—"))
        ttk.Label(photo_controls, textvariable=self.photo_current_var,
                  wraplength=470).pack(anchor="w", pady=(2, 10))
        self.photo_file_var = tk.StringVar(value=self.t["photo_none"])
        ttk.Label(photo_controls, textvariable=self.photo_file_var,
                  wraplength=470, foreground=self.INK_MUTED).pack(anchor="w", pady=(0, 8))
        ttk.Button(photo_controls, text=self.t["photo_choose"],
                   command=self._choose_photo).pack(anchor="w")
        self.photo_remove_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(photo_controls, text=self.t["photo_remove"],
                        variable=self.photo_remove_var).pack(anchor="w", pady=(8, 14))

        ttk.Label(photo_controls, text=self.t["photo_zoom"]).pack(anchor="w")
        self.photo_zoom_var = tk.DoubleVar(value=1.0)
        ttk.Scale(photo_controls, from_=0.45, to=2.5,
                  variable=self.photo_zoom_var,
                  command=lambda _value: self._render_photo()).pack(fill="x", pady=(0, 10))
        edge_head = ttk.Frame(photo_controls)
        edge_head.pack(fill="x")
        ttk.Label(edge_head, text=self.t["photo_edge"]).pack(side="left")
        self.photo_cleanup_readout = tk.StringVar(value="1 px")
        ttk.Label(edge_head, textvariable=self.photo_cleanup_readout,
                  foreground=self.INK_MUTED).pack(side="right")
        self.photo_cleanup_var = tk.DoubleVar(value=1.0)
        ttk.Scale(photo_controls, from_=0, to=12,
                  variable=self.photo_cleanup_var,
                  command=self._photo_cleanup_changed).pack(fill="x", pady=(0, 10))

        exposure_head = ttk.Frame(photo_controls)
        exposure_head.pack(fill="x")
        ttk.Label(exposure_head, text=self.t["photo_exposure"]).pack(side="left")
        self.photo_exposure_readout = tk.StringVar(value="0.0 EV")
        ttk.Label(exposure_head, textvariable=self.photo_exposure_readout,
                  foreground=self.INK_MUTED).pack(side="right")
        self.photo_exposure_var = tk.DoubleVar(value=0.0)
        ttk.Scale(photo_controls, from_=-2, to=2,
                  variable=self.photo_exposure_var,
                  command=self._photo_exposure_changed).pack(fill="x", pady=(0, 8))

        contrast_head = ttk.Frame(photo_controls)
        contrast_head.pack(fill="x")
        ttk.Label(contrast_head, text=self.t["photo_contrast"]).pack(side="left")
        self.photo_contrast_readout = tk.StringVar(value="0")
        ttk.Label(contrast_head, textvariable=self.photo_contrast_readout,
                  foreground=self.INK_MUTED).pack(side="right")
        self.photo_contrast_var = tk.DoubleVar(value=0.0)
        ttk.Scale(photo_controls, from_=-100, to=100,
                  variable=self.photo_contrast_var,
                  command=self._photo_contrast_changed).pack(fill="x", pady=(0, 8))

        saturation_head = ttk.Frame(photo_controls)
        saturation_head.pack(fill="x")
        ttk.Label(saturation_head, text=self.t["photo_saturation"]).pack(side="left")
        self.photo_saturation_readout = tk.StringVar(value="0")
        ttk.Label(saturation_head, textvariable=self.photo_saturation_readout,
                  foreground=self.INK_MUTED).pack(side="right")
        self.photo_saturation_var = tk.DoubleVar(value=0.0)
        ttk.Scale(photo_controls, from_=-100, to=100,
                  variable=self.photo_saturation_var,
                  command=self._photo_saturation_changed).pack(fill="x", pady=(0, 8))

        self.photo_sepia_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(photo_controls, text=self.t["photo_sepia"],
                        variable=self.photo_sepia_var,
                        command=self._photo_sepia_toggled).pack(anchor="w")
        sepia_head = ttk.Frame(photo_controls)
        sepia_head.pack(fill="x")
        ttk.Label(sepia_head, text=self.t["photo_sepia_strength"]).pack(side="left")
        self.photo_sepia_readout = tk.StringVar(value="60%")
        ttk.Label(sepia_head, textvariable=self.photo_sepia_readout,
                  foreground=self.INK_MUTED).pack(side="right")
        self.photo_sepia_strength_var = tk.DoubleVar(value=60.0)
        self.photo_sepia_scale = ttk.Scale(
            photo_controls, from_=0, to=100,
            variable=self.photo_sepia_strength_var,
            command=self._photo_sepia_changed, state="disabled",
        )
        self.photo_sepia_scale.pack(fill="x", pady=(0, 8))
        ttk.Button(photo_controls, text=self.t["photo_adjust_reset"],
                   command=self._reset_photo_adjustments).pack(anchor="w", pady=(0, 8))
        ttk.Button(photo_controls, text=self.t["photo_reset"],
                   command=self._reset_photo_position).pack(anchor="w")
        ttk.Label(photo_controls, text=self.t["photo_drag"], wraplength=470,
                  foreground=self.INK_MUTED).pack(anchor="w", pady=(8, 20))

        actions = ttk.Frame(photo_controls)
        actions.pack(fill="x")
        self.photo_apply_btn = ttk.Button(
            actions, text=self.t["photo_apply"], command=self._apply_photo,
            state="disabled")
        self.photo_apply_btn.pack(side="left")
        self.photo_restore_btn = ttk.Button(
            actions, text=self.t["photo_restore"], command=self._restore_photo,
            state="disabled")
        self.photo_restore_btn.pack(side="left", padx=8)

        self.photo_source: Optional[Image.Image] = None
        self.photo_background: Optional[Image.Image] = None
        self.photo_preview: Optional[Image.Image] = None
        self.photo_tk: Optional[ImageTk.PhotoImage] = None
        self.photo_center = [pilot_photo.PORTRAIT_SIZE / 2,
                             pilot_photo.PORTRAIT_SIZE / 2]
        self.photo_drag_at: Optional[tuple[int, int]] = None
        try:
            with Image.open(pilot_photo.background_path()) as source_background:
                self.photo_background = source_background.convert("RGB")
        except OSError:
            self.photo_background = Image.new(
                "RGB", (pilot_photo.PORTRAIT_SIZE, pilot_photo.PORTRAIT_SIZE),
                self.PAPER)
        self._render_photo()

        # -- own biography tab: the text lives with the tracker (custombio),
        # never in the game or the career file - the game shows a biography
        # only while a career is being created.
        bio = ttk.Frame(nb)
        nb.add(bio, text=self.t["tab_bio"])
        ttk.Label(bio, text=self.t["bio_intro"], wraplength=1080,
                  foreground="#444").pack(anchor="w", padx=8, pady=(8, 2))
        ttk.Label(bio, text=self.t["bio_vars"], wraplength=1080,
                  foreground=self.INK_MUTED).pack(anchor="w", padx=8, pady=(0, 6))
        self.bio_source_var = tk.StringVar()
        ttk.Label(bio, textvariable=self.bio_source_var,
                  foreground=self.ACCENT_DARK).pack(anchor="w", padx=8)
        bio_body = ttk.Frame(bio)
        bio_body.pack(fill="both", expand=True, padx=8, pady=(4, 8))
        bio_left = ttk.Frame(bio_body)
        bio_left.pack(side="left", fill="both", expand=True)
        # Packed before the text so they keep their place at any height: the
        # medal and booster column beside the text is the tall one.
        bio_actions = ttk.Frame(bio_left)
        bio_actions.pack(side="bottom", fill="x", pady=(8, 0))
        self.bio_save_btn = ttk.Button(bio_actions, text=self.t["bio_save"],
                                       command=self._save_bio, state="disabled")
        self.bio_save_btn.pack(side="left")
        self.bio_restore_btn = ttk.Button(bio_actions, text=self.t["bio_restore"],
                                          command=self._restore_bio, state="disabled")
        self.bio_restore_btn.pack(side="left", padx=8)
        self.bio_count_var = tk.StringVar()
        ttk.Label(bio_actions, textvariable=self.bio_count_var,
                  foreground=self.INK_MUTED).pack(side="right")
        bio_text_frame = ttk.Frame(bio_left)
        bio_text_frame.pack(side="top", fill="both", expand=True)
        self.bio_text = tk.Text(
            # width/height are only the minimum asked for; pack's expand gives
            # it the room left beside the medals. Tk's default 80 columns of
            # Georgia pushed the medal panel out of the window.
            bio_text_frame, width=40, height=10, wrap="word", undo=True, font=("Georgia", 11),
            background=self.PAPER, foreground=self.INK, insertbackground=self.INK,
            relief="flat", highlightthickness=1, highlightbackground=self.BORDER,
            padx=10, pady=8)
        bio_scroll = ttk.Scrollbar(bio_text_frame, orient="vertical",
                                   command=self.bio_text.yview)
        self.bio_text.configure(yscrollcommand=bio_scroll.set)
        bio_scroll.pack(side="right", fill="y")
        self.bio_text.pack(side="left", fill="both", expand=True)
        self.bio_text.bind("<<Modified>>", self._bio_modified)

        # The medal and booster column scrolls when it is taller than the
        # tab - Russian medal names wrap to three lines, and the window may be
        # as short as 700 px. Same construction as the Flights tab; the bar
        # only shows when it is needed.
        bio_side_canvas = tk.Canvas(bio_body, borderwidth=0, highlightthickness=0,
                                    background=self.PANEL, width=350)
        bio_side_bar = ttk.Scrollbar(bio_body, orient="vertical",
                                     command=bio_side_canvas.yview)
        bio_side_canvas.configure(yscrollcommand=bio_side_bar.set)
        bio_side_bar.pack(side="right", fill="y")
        bio_side_canvas.pack(side="left", fill="y", padx=(14, 0))
        bio_side = ttk.Frame(bio_side_canvas)
        bio_side_canvas.create_window((0, 0), window=bio_side, anchor="nw")

        def _bio_side_fit(_event=None):
            bio_side_canvas.configure(scrollregion=bio_side_canvas.bbox("all"),
                                      width=bio_side.winfo_reqwidth())
            if bio_side.winfo_reqheight() > bio_side_canvas.winfo_height() > 1:
                bio_side_bar.pack(side="right", fill="y")
            else:
                bio_side_bar.pack_forget()
                bio_side_canvas.yview_moveto(0)
        bio_side.bind("<Configure>", _bio_side_fit)
        bio_side_canvas.bind("<Configure>", _bio_side_fit)

        def _bio_side_wheel(event):
            if bio_side_bar.winfo_ismapped():
                bio_side_canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
        bio_side_canvas.bind("<Enter>", lambda _e: bio_side_canvas.bind_all("<MouseWheel>", _bio_side_wheel))
        bio_side_canvas.bind("<Leave>", lambda _e: bio_side_canvas.unbind_all("<MouseWheel>"))
        self.bio_medals_frame = ttk.LabelFrame(bio_side, text=self.t["bio_medals"])
        self.bio_medals_frame.pack(fill="x")

        # Boosters: the biography's points shared out again. Unlike the text
        # this writes pilot.leadLevel, so it has its own button.
        boost = ttk.LabelFrame(bio_side, text=self.t["bio_boost"])
        boost.pack(fill="x", pady=(14, 0))
        self.bio_boost_intro_var = tk.StringVar()
        ttk.Label(boost, textvariable=self.bio_boost_intro_var, wraplength=320,
                  foreground=self.INK_MUTED).pack(anchor="w", padx=8, pady=(6, 4))
        self.bio_boost_vars: Dict[str, tk.IntVar] = {}
        self.bio_boost_spins: List[ttk.Spinbox] = []
        # the panel's order, the game's own names
        for key, game_key, ours in (
                ("skill", "carPilotCharacteristics_SkillBooster", "pend_col_sk"),
                ("discipline", "carPilotCharacteristics_DisciplineBooster", "pend_col_di"),
                ("courage", "carPilotCharacteristics_CourageBooster", "pend_col_co")):
            row = ttk.Frame(boost)
            row.pack(fill="x", padx=8, pady=1)
            ttk.Label(row, text=self.game_t.get(game_key) or self.t[ours]).pack(side="left")
            var = tk.IntVar(value=0)
            spin = ttk.Spinbox(row, from_=0, to=custombio.BOOSTER_MAX, width=4,
                               textvariable=var, state="disabled",
                               command=self._bio_boost_changed)
            spin.pack(side="right")
            self.bio_boost_vars[key] = var
            self.bio_boost_spins.append(spin)
        self.bio_boost_left_var = tk.StringVar()
        ttk.Label(boost, textvariable=self.bio_boost_left_var,
                  foreground=self.ACCENT_DARK).pack(anchor="w", padx=8, pady=(4, 0))
        self.bio_boost_btn = ttk.Button(boost, text=self.t["bio_boost_apply"],
                                        command=self._apply_boosters, state="disabled")
        self.bio_boost_btn.pack(anchor="w", fill="x", padx=8, pady=(6, 8))
        self.bio_boost_total = 0
        # the boosters as the box read them; the write is refused if the
        # career holds anything else by then
        self.bio_boost_current: Optional[Dict[str, int]] = None
        self.bio_boost_lead: Optional[int] = None
        self.bio_info: Optional[Dict[str, Any]] = None
        self.bio_game_text = ""
        self.bio_inferred: tuple = ()
        self.bio_medal_vars: List[tuple] = []

        # -- flights tab
        fl = ttk.Frame(nb)
        nb.add(fl, text=self.t["tab_flights"])
        # The eastern board is a commander pair and three squadrons - taller
        # than the window on any ordinary screen - so the whole tab scrolls,
        # not just the seats: the bench and the buttons belong below it and
        # must stay reachable. A canvas with a frame inside it is the only
        # way Tk does this.
        fl_canvas = tk.Canvas(fl, borderwidth=0, highlightthickness=0,
                              background=self.PANEL)
        fl_bar = ttk.Scrollbar(fl, orient="vertical", command=fl_canvas.yview)
        fl_canvas.configure(yscrollcommand=fl_bar.set)
        fl_bar.pack(side="right", fill="y")
        fl_canvas.pack(side="left", fill="both", expand=True)
        body = tk.Frame(fl_canvas, background=self.PANEL)
        fl_window = fl_canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind("<Configure>",
                  lambda _e: fl_canvas.configure(scrollregion=fl_canvas.bbox("all")))
        # The inner frame follows the canvas's width so the wrapped text and
        # the bench stretch with the window instead of being clipped.
        fl_canvas.bind("<Configure>",
                       lambda e: fl_canvas.itemconfigure(fl_window, width=e.width))

        # The wheel is bound while the pointer is over this tab and released
        # when it leaves, so it cannot steal scrolling from the other tabs.
        def _fl_wheel(event):
            fl_canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")
        fl_canvas.bind("<Enter>", lambda _e: fl_canvas.bind_all("<MouseWheel>", _fl_wheel))
        fl_canvas.bind("<Leave>", lambda _e: fl_canvas.unbind_all("<MouseWheel>"))
        ttk.Label(body, text=self.t["fl_intro"], wraplength=1080,
                  foreground="#444").pack(anchor="w", padx=8, pady=(8, 6))
        self.fl_men: Dict[int, Dict] = {}
        self.fl_plan: Dict[int, Optional[int]] = {}
        self.fl_cards: Dict[int, tuple] = {}
        self.fl_heads: Dict[int, tk.Label] = {}
        self.fl_alert: set = set()
        self.fl_pick: Optional[int] = None
        board = tk.Frame(body, background=self.PANEL)
        board.pack(anchor="w", padx=8)
        self.fl_board = board
        self.fl_seats = Career.SEATS
        self.fl_groups: List[Group] = line_up_shape(601, Career.SEATS, self.t, self.game_t)
        self._build_board(board, self.fl_groups)
        tk.Label(body, text="\u2605 " + self.t["fl_cmd"], background=self.PANEL,
                 foreground=self.ACCENT, font=("", 9), anchor="w").pack(
            anchor="w", padx=10, pady=(8, 0))
        tk.Label(body, text=self.t["fl_legend"], background=self.PANEL,
                 foreground=self.INK_MUTED, font=("", 9), anchor="w",
                 justify="left", wraplength=1060).pack(anchor="w", padx=10, pady=(2, 0))
        ttk.Separator(body).pack(fill="x", padx=8, pady=(10, 6))
        tk.Label(body, text=self.t["fl_bench"], background=self.PANEL,
                 foreground=self.ACCENT_DARK, font=("Georgia", 10, "bold"),
                 anchor="w").pack(anchor="w", padx=10)
        tk.Label(body, text=self.t["fl_bench_hint"], background=self.PANEL,
                 foreground=self.INK_MUTED, font=("", 9), anchor="w").pack(
            anchor="w", padx=10, pady=(0, 4))
        bcols = ("who", "stats", "ai", "boost", "state")
        self.bench_tree = ttk.Treeview(body, columns=bcols, show="headings",
                                       height=5, selectmode="browse")
        self.bench_tree.tag_configure("odd", background=self.STRIPE)
        self.bench_tree.tag_configure("gone", foreground=self.BAD)
        for col, head, width in (
                ("who", self.t["pend_col_who"], 180),
                ("stats", self.t["fl_b_stats"], 90),
                ("ai", self.t["fl_ai"], 60),
                ("boost", self.t["fl_b_boost"], 90),
                ("state", self.t["pend_col_status"], 120)):
            self.bench_tree.heading(col, text=head, anchor="w")
            self.bench_tree.column(col, width=width, anchor="w")
        self.bench_tree.pack(fill="x", padx=10, pady=(0, 4))
        self.bench_tree.bind("<<TreeviewSelect>>", self._pick_bench)
        self.fl_up: Optional[int] = None

        frow = ttk.Frame(body)
        frow.pack(anchor="w", padx=8, pady=(8, 10))
        ttk.Button(frow, text=self.t["fl_propose"],
                   command=self._propose_seats).pack(side="left")
        ttk.Button(frow, text=self.t["fl_reset"],
                   command=self._fill_flights).pack(side="left", padx=8)
        ttk.Button(frow, text=self.t["fl_apply"],
                   command=self._apply_seats).pack(side="left")
        self.fl_pool_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(frow, text=self.t["fl_use_pool"],
                        variable=self.fl_pool_var).pack(side="left", padx=12)
        self.fl_var = tk.StringVar(value=self.t["fl_hint"])
        ttk.Label(frow, textvariable=self.fl_var).pack(side="left", padx=10)

        self.status = tk.StringVar()
        ttk.Label(self, textvariable=self.status, wraplength=820,
                  foreground=self.INK_MUTED).pack(
            fill="x", padx=10, pady=(0, 8))

    # -- data ------------------------------------------------------------------

    def _load_careers(self) -> None:
        game = find_game_dir()
        if game is None:
            self.status.set(self.t["no_game"])
            return
        self.careers = list_careers(game)
        if not self.careers:
            self.status.set(self.t["no_careers"])
            return
        self.career_box["values"] = [c.name for c in self.careers]
        self.career_box.current(0)
        self._select_career()

    def _refresh(self) -> None:
        current = self.career_var.get()
        self._load_careers()
        if current in [c.name for c in self.careers]:
            self.career_box.set(current)
            self._select_career()

    def _select_career(self) -> None:
        name = self.career_var.get()
        self.career = next((c for c in self.careers if c.name == name), None)
        if self.career is None:
            return
        try:
            today = self.career.current_date()
            self.lost = self.career.lost_pilots()
            self.downed = self.career.downed_pilots()
            points = self.career.award_points()
        except sqlite3.Error as exc:
            self.status.set(self.t["failed"].format(error=exc))
            return
        self.rule_var.set(self.t["rule"].format(date=today))
        self.tree.delete(*self.tree.get_children())
        for n, p in enumerate(self.lost):
            self.tree.insert("", "end", iid=str(p["id"]), tags=("odd",) if n % 2 else (), values=(
                p["name"], self.t[STATE_NAMES[p["state"]]], p["lost_on"],
                self.t["yes"] if p["revivable"] else self.t["no"]))
        if not self.lost:
            self.status.set(self.t["no_dead"])
        else:
            self.status.set("")
        self.cap_tree.delete(*self.cap_tree.get_children())
        for d in self.downed:
            fate = (self.t["fate_evading"].format(date=d["back_on"]) if d["evading"]
                    else self.t["fate_lost_plane"])
            self.cap_tree.insert("", "end", iid=str(d["id"]),
                                 tags=("odd",) if len(self.cap_tree.get_children()) % 2 else (),
                                 values=(
                d["name"], d["date"], fate, self.t["yes"] if d["capturable"] else self.t["no_later"]))
        self.points_var.set(self.t["points_now"].format(points=points))
        self._update_buttons()
        self._fill_times()
        self._fill_pending()
        self._fill_photo()
        self._fill_bio()
        self._fill_flights()

    # -- custom pilot photo --------------------------------------------------

    def _fill_photo(self) -> None:
        if self.career is None:
            self.photo_current_var.set(self.t["photo_current"].format(path="—"))
            self.photo_restore_btn["state"] = "disabled"
            return
        try:
            player = self.career.player_portrait()
        except (sqlite3.Error, ValueError) as exc:
            self.photo_current_var.set(self.t["failed"].format(error=exc))
            self.photo_restore_btn["state"] = "disabled"
            return
        self.photo_current_var.set(
            self.t["photo_current"].format(path=player["avatar_path"] or "—"))
        # Until a new photo is chosen the preview shows the portrait the
        # career uses now - a loose custom DDS or the game's own.
        self.photo_current = None
        game = find_game_dir()
        if game is not None and player["avatar_path"]:
            try:
                data = AssetResolver(game).read(f"nsdata/assets/pilotphotos/{player['avatar_path']}.dds")
                if data:
                    self.photo_current = Image.open(io.BytesIO(data)).convert("RGB")
            except Exception:     # noqa: BLE001 - no preview is not an error
                self.photo_current = None
        if getattr(self, "photo_source", None) is None:
            self._render_photo()
        state = pilot_photo.load_state(self.career.path)
        can_restore = bool(state and state.get("pilot_id") == player["id"] and
                           not is_custom(state.get("original_avatar_path", "custom/")))
        self.photo_restore_btn["state"] = "normal" if can_restore else "disabled"

    def _render_photo(self) -> None:
        if not hasattr(self, "photo_canvas") or self.photo_background is None:
            return
        if self.photo_source is None:
            image = (getattr(self, "photo_current", None) or self.photo_background).resize(
                (pilot_photo.PORTRAIT_SIZE, pilot_photo.PORTRAIT_SIZE),
                Image.Resampling.LANCZOS)
        else:
            image = pilot_photo.compose_portrait(
                self.photo_source, self.photo_background,
                zoom=self.photo_zoom_var.get(),
                center_x=self.photo_center[0], center_y=self.photo_center[1],
                cleanup=self.photo_cleanup_var.get(),
                exposure=self.photo_exposure_var.get(),
                contrast=self.photo_contrast_var.get(),
                saturation=self.photo_saturation_var.get(),
                sepia_strength=(self.photo_sepia_strength_var.get() / 100
                                if self.photo_sepia_var.get() else 0),
            )
        self.photo_preview = image
        self.photo_tk = ImageTk.PhotoImage(image)
        self.photo_canvas.delete("all")
        self.photo_canvas.create_image(0, 0, image=self.photo_tk, anchor="nw")

    def _reset_photo_position(self) -> None:
        self.photo_center[:] = [pilot_photo.PORTRAIT_SIZE / 2,
                                pilot_photo.PORTRAIT_SIZE / 2]
        self.photo_zoom_var.set(1.0)
        self._render_photo()

    def _reset_photo_adjustments(self) -> None:
        self.photo_cleanup_var.set(1.0)
        self.photo_cleanup_readout.set("1 px")
        self.photo_exposure_var.set(0.0)
        self.photo_exposure_readout.set("0.0 EV")
        self.photo_contrast_var.set(0.0)
        self.photo_contrast_readout.set("0")
        self.photo_saturation_var.set(0.0)
        self.photo_saturation_readout.set("0")
        self.photo_sepia_var.set(False)
        self.photo_sepia_strength_var.set(60.0)
        self.photo_sepia_readout.set("60%")
        self.photo_sepia_scale["state"] = "disabled"
        self._render_photo()

    def _photo_cleanup_changed(self, value: str) -> None:
        pixels = round(float(value))
        self.photo_cleanup_readout.set(f"{pixels} px")
        self._render_photo()

    def _photo_exposure_changed(self, value: str) -> None:
        exposure = round(float(value), 1)
        self.photo_exposure_readout.set(f"{exposure:+.1f} EV" if exposure else "0.0 EV")
        self._render_photo()

    def _photo_contrast_changed(self, value: str) -> None:
        contrast = round(float(value))
        self.photo_contrast_readout.set(f"{contrast:+d}" if contrast else "0")
        self._render_photo()

    def _photo_saturation_changed(self, value: str) -> None:
        saturation = round(float(value))
        self.photo_saturation_readout.set(f"{saturation:+d}" if saturation else "0")
        self._render_photo()

    def _photo_sepia_toggled(self) -> None:
        self.photo_sepia_scale["state"] = (
            "normal" if self.photo_sepia_var.get() else "disabled"
        )
        self._render_photo()

    def _photo_sepia_changed(self, value: str) -> None:
        self.photo_sepia_readout.set(f"{round(float(value))}%")
        self._render_photo()

    def _photo_drag_start(self, event) -> None:
        self.photo_drag_at = (event.x, event.y)

    def _photo_drag_move(self, event) -> None:
        if self.photo_source is None or self.photo_drag_at is None:
            return
        old_x, old_y = self.photo_drag_at
        self.photo_center[0] += event.x - old_x
        self.photo_center[1] += event.y - old_y
        self.photo_drag_at = (event.x, event.y)
        self._render_photo()

    def _choose_photo(self) -> None:
        chosen = filedialog.askopenfilename(
            parent=self, title=self.t["photo_choose"],
            filetypes=[(self.t["photo_filetypes"], "*.jpg *.jpeg *.png *.webp *.bmp"),
                       ("PNG", "*.png"), ("JPEG", "*.jpg *.jpeg")],
        )
        if not chosen:
            return
        try:
            source = pilot_photo.load_photo(Path(chosen))
            if self.photo_remove_var.get() and not pilot_photo.has_useful_alpha(source):
                self.status.set(self.t["photo_working"])
                self.configure(cursor="wait")
                self.update_idletasks()
                source = pilot_photo.remove_background(source)
        except Exception as exc:          # noqa: BLE001 - presented in the UI
            messagebox.showerror(self.t["title"], self.t["failed"].format(error=exc))
            return
        finally:
            self.configure(cursor="")
        self.photo_source = source
        self.photo_file_var.set(str(chosen))
        self.photo_apply_btn["state"] = "normal"
        self._reset_photo_position()
        self._reset_photo_adjustments()
        self.status.set(self.t["photo_ready"])

    def _apply_photo(self) -> None:
        if self.career is None or self.photo_source is None or self.photo_background is None:
            return
        game = find_game_dir()
        if game is None:
            self.status.set(self.t["no_game"])
            return
        try:
            player = self.career.player_portrait()
            avatar = pilot_photo.custom_avatar_path(self.career.path, player["id"])
            destination = pilot_photo.portrait_destination(game, avatar)
            composed = pilot_photo.compose_portrait(
                self.photo_source, self.photo_background,
                zoom=self.photo_zoom_var.get(),
                center_x=self.photo_center[0], center_y=self.photo_center[1],
                cleanup=self.photo_cleanup_var.get(),
                exposure=self.photo_exposure_var.get(),
                contrast=self.photo_contrast_var.get(),
                saturation=self.photo_saturation_var.get(),
                sepia_strength=(self.photo_sepia_strength_var.get() / 100
                                if self.photo_sepia_var.get() else 0),
            )
            pilot_photo.convert_to_dds(composed, destination)
            state = pilot_photo.load_state(self.career.path)
            if not state or state.get("pilot_id") != player["id"]:
                state = {"career": str(self.career.path), "pilot_id": player["id"]}
                # Only a game portrait is an original. A custom one already in
                # the career was set by an earlier photo whose record this copy
                # cannot see (a source run keeps its own); remembering it as the
                # "original" made Restore put an old custom path back.
                if not is_custom(player["avatar_path"]):
                    state["original_avatar_path"] = player["avatar_path"]
            state["custom_avatar_path"] = avatar
            pilot_photo.save_state(self.career.path, state)
            backup = self.career.set_player_portrait(avatar)
        except sqlite3.OperationalError:
            messagebox.showerror(self.t["title"], self.t["locked"])
            return
        except Exception as exc:          # noqa: BLE001 - presented in the UI
            messagebox.showerror(self.t["title"], self.t["failed"].format(error=exc))
            return
        self.status.set(self.t["photo_applied"].format(
            name=player["name"], path=destination, backup=backup))
        self._fill_photo()

    def _restore_photo(self) -> None:
        if self.career is None:
            return
        state = pilot_photo.load_state(self.career.path)
        try:
            player = self.career.player_portrait()
            if not state or state.get("pilot_id") != player["id"] or \
                    is_custom(state.get("original_avatar_path", "custom/")):
                self.status.set(self.t["photo_no_restore"])
                self._fill_photo()
                return
            backup = self.career.set_player_portrait(state["original_avatar_path"])
        except sqlite3.OperationalError:
            messagebox.showerror(self.t["title"], self.t["locked"])
            return
        except Exception as exc:          # noqa: BLE001 - presented in the UI
            messagebox.showerror(self.t["title"], self.t["failed"].format(error=exc))
            return
        pilot_photo.clear_state(self.career.path)
        self.status.set(self.t["photo_restored"].format(
            name=player["name"], backup=backup))
        self._fill_photo()

    # -- own biography -------------------------------------------------------

    def _bio_set_text(self, text: str) -> None:
        self.bio_text.delete("1.0", "end")
        self.bio_text.insert("1.0", text)
        self.bio_text.edit_reset()
        self.bio_text.edit_modified(False)
        self._bio_count()

    def _bio_count(self) -> None:
        n = len(self.bio_text.get("1.0", "end").strip())
        self.bio_count_var.set(self.t["bio_count"].format(n=n, max=custombio.MAX_LENGTH))

    def _bio_modified(self, _event=None) -> None:
        if self.bio_text.edit_modified():
            self._bio_count()
            self.bio_text.edit_modified(False)

    def _fill_bio(self) -> None:
        self.bio_info = None
        self.bio_game_text = ""
        self._bio_set_text("")
        for child in self.bio_medals_frame.winfo_children():
            child.destroy()
        self.bio_medal_vars = []
        self.bio_save_btn["state"] = "disabled"
        self.bio_restore_btn["state"] = "disabled"
        if self.career is None:
            self.bio_source_var.set("")
            return
        try:
            info = self.career.player_biography()
        except (sqlite3.Error, ValueError) as exc:
            self.bio_source_var.set(self.t["failed"].format(error=exc))
            return
        self.bio_info = info
        game_lang = GAME_LANGS.get(self.lang, "eng")
        raw = None
        game = find_game_dir()
        if game is not None and info["biography_id"]:
            try:
                resolver = AssetResolver(game)
                for code in dict.fromkeys((game_lang, "eng")):
                    raw = resolver.read_text(
                        "nsdata/assets/characterbio/"
                        f"bio.id={info['biography_id']}.locale={code}.txt")
                    if raw:
                        break
            except Exception:            # noqa: BLE001 - an empty editor is still usable
                raw = None
        self.bio_game_text = custombio.editable(raw or "")
        own = custombio.load(self.career.path, info["id"])
        if own and own["text"]:
            self._bio_set_text(own["text"])
            self.bio_source_var.set(self.t["bio_source_own"].format(
                date=(own.get("updated") or "")[:10] or "—"))
        else:
            self._bio_set_text(self.bio_game_text)
            self.bio_source_var.set(self.t["bio_source_game"] if self.bio_game_text
                                    else self.t["bio_none"])

        # The medals: the player's own choice once made, otherwise what the
        # chosen biography implies - the same rule the Service Record uses.
        country = info["country"]
        self.bio_inferred = wwii_awards.for_career_description(info["description"], country)
        selected = set(own["wwii_awards"] if own and own["wwii_awards"] is not None
                       else self.bio_inferred)
        families = wwii_awards.CHOICES.get(country, ())
        if not families:
            ttk.Label(self.bio_medals_frame, text=self.t["bio_medals_nation"],
                      wraplength=320, foreground=self.INK_MUTED).pack(anchor="w", padx=8, pady=6)
        else:
            stars = False
            for family, ids in families:
                label = wwii_awards.family_name(family, game_lang)
                if len(ids) == 1:
                    var = tk.BooleanVar(value=ids[0] in selected)
                    ttk.Checkbutton(self.bio_medals_frame, text=label, variable=var
                                    ).pack(anchor="w", padx=8, pady=2)
                    self.bio_medal_vars.append((ids, var))
                    continue
                stars = True
                ttk.Label(self.bio_medals_frame, text=label, wraplength=320
                          ).pack(anchor="w", padx=8, pady=(6, 0))
                plain = self.t["bio_medal_plain"]
                values = [self.t["bio_medal_none"], plain] + [
                    f"{plain} {'★' * n}" for n in range(1, len(ids))]
                picked = [ids.index(a) + 1 for a in ids if a in selected]
                box = ttk.Combobox(self.bio_medals_frame, values=values,
                                   state="readonly", width=22)
                box.current(max(picked) if picked else 0)
                box.pack(anchor="w", padx=(24, 8), pady=(2, 2))
                self.bio_medal_vars.append((ids, box))
            if stars:
                ttk.Label(self.bio_medals_frame, text=self.t["bio_stars_hint"],
                          foreground=self.INK_MUTED).pack(anchor="w", padx=8, pady=(4, 6))
        self.bio_save_btn["state"] = "normal"
        self.bio_restore_btn["state"] = (
            "normal" if own and (own["text"] or own["wwii_awards"] is not None) else "disabled")
        self._fill_boosters(info, own, game)

    def _boost_name(self, key: str) -> str:
        game_key, ours = {
            "skill": ("carPilotCharacteristics_SkillBooster", "pend_col_sk"),
            "discipline": ("carPilotCharacteristics_DisciplineBooster", "pend_col_di"),
            "courage": ("carPilotCharacteristics_CourageBooster", "pend_col_co"),
        }[key]
        return self.game_t.get(game_key) or self.t[ours]

    def _boost_text(self, values: Dict[str, int]) -> str:
        return " · ".join(f"{self._boost_name(k)} {values[k]}"
                          for k in ("skill", "discipline", "courage"))

    def _fill_boosters(self, info: Dict[str, Any], own: Optional[Dict[str, Any]],
                       game: Optional[Path]) -> None:
        self.bio_boost_current = None
        self.bio_boost_lead = None
        self.bio_boost_total = 0
        self.bio_boost_left_var.set("")
        self.bio_boost_btn["state"] = "disabled"
        points = None
        if game is not None and info["biography_id"]:
            try:
                raw = AssetResolver(game).read_text("nsdata/assets/characterbio/info.json")
                points = custombio.biography_points(loads_lenient(raw), info["biography_id"]) if raw else None
            except Exception:            # noqa: BLE001 - shown as "cannot be shared out"
                points = None
        if points is None:
            self.bio_boost_intro_var.set(self.t["bio_boost_unknown"])
            for spin in self.bio_boost_spins:
                spin["state"] = "disabled"
            for var in self.bio_boost_vars.values():
                var.set(0)
            return
        # Everything the pilot has is shared out again, promotion points
        # included (custombio): the box shows what the career holds.
        current = custombio.boosters(info["lead_level"])
        biography = sum(points.values())
        total = sum(current.values())
        cap = custombio.booster_cap(biography, current)
        self.bio_boost_current = current
        self.bio_boost_lead = info["lead_level"]
        self.bio_boost_total = total
        self.bio_boost_cap = cap
        for key, var in self.bio_boost_vars.items():
            var.set(current[key])
        for spin in self.bio_boost_spins:
            spin.configure(to=cap, state="readonly")
        self.bio_boost_intro_var.set(self.t["bio_boost_intro"].format(
            total=total, bio=min(biography, total), promo=max(0, total - biography), max=cap))
        self._bio_boost_changed()

    def _bio_boost_chosen(self) -> Dict[str, int]:
        return {key: int(var.get()) for key, var in self.bio_boost_vars.items()}

    def _bio_boost_changed(self) -> None:
        if self.bio_boost_current is None:
            return
        chosen = self._bio_boost_chosen()
        left = self.bio_boost_total - sum(chosen.values())
        self.bio_boost_left_var.set(
            self.t["bio_boost_done"].format(total=self.bio_boost_total) if left == 0 else
            self.t["bio_boost_left"].format(n=left, total=self.bio_boost_total))
        self.bio_boost_btn["state"] = (
            "normal" if left == 0 and chosen != self.bio_boost_current else "disabled")

    def _apply_boosters(self) -> None:
        if self.career is None or self.bio_boost_current is None:
            return
        chosen = self._bio_boost_chosen()
        try:
            custombio.check_allocation(chosen, self.bio_boost_total, self.bio_boost_cap)
            lead = custombio.repack(self.bio_boost_lead, chosen)
            backup = self.career.set_player_boosters(self.bio_boost_lead, lead)
        except sqlite3.OperationalError:
            messagebox.showerror(self.t["title"], self.t["locked"])
            return
        except Exception as exc:          # noqa: BLE001 - presented in the UI
            messagebox.showerror(self.t["title"], self.t["failed"].format(error=exc))
            return
        name = self.bio_info["name"] if self.bio_info else ""
        self._fill_bio()
        self.status.set(self.t["bio_boost_applied"].format(
            name=name, values=self._boost_text(custombio.boosters(lead)), backup=backup))

    def _bio_selected_awards(self) -> List[int]:
        out = []
        for ids, widget in self.bio_medal_vars:
            if isinstance(widget, tk.BooleanVar):
                if widget.get():
                    out.append(ids[0])
            else:
                index = widget.current()
                if index > 0:
                    out.append(ids[index - 1])
        return out

    def _save_bio(self) -> None:
        if self.career is None or self.bio_info is None:
            return
        info = self.bio_info
        text = self.bio_text.get("1.0", "end").strip()
        if len(text) > custombio.MAX_LENGTH:
            messagebox.showerror(self.t["title"], self.t["bio_too_long"].format(
                n=len(text), max=custombio.MAX_LENGTH))
            return
        unknown = custombio.unknown_variables(text)
        if unknown and not messagebox.askyesno(
                self.t["title"], self.t["bio_unknown"].format(vars="\n".join(unknown))):
            return
        # Unchanged text and medals are not stored, so the record only ever
        # holds what the player actually changed.
        own_text = (None if custombio.paragraphs(text) == custombio.paragraphs(self.bio_game_text)
                    else text)
        awards = None
        if self.bio_medal_vars:
            country = info["country"]
            picked = wwii_awards.chosen(self._bio_selected_awards(), country)
            if picked != wwii_awards.chosen(self.bio_inferred, country):
                awards = list(picked)
        try:
            if own_text is None and awards is None:
                custombio.clear(self.career.path, info["id"])
            else:
                custombio.save(self.career.path, info["id"], info["country"], own_text, awards)
        except Exception as exc:          # noqa: BLE001 - presented in the UI
            messagebox.showerror(self.t["title"], self.t["failed"].format(error=exc))
            return
        self._fill_bio()
        self.status.set(self.t["bio_saved"].format(name=info["name"]))

    def _restore_bio(self) -> None:
        if self.career is None or self.bio_info is None:
            return
        name = self.bio_info["name"]
        custombio.clear(self.career.path, self.bio_info["id"])
        self._fill_bio()
        self.status.set(self.t["bio_restored"].format(name=name))

    def _selected(self) -> Optional[Dict]:
        sel = self.tree.selection()
        if not sel:
            return None
        return next((p for p in self.lost if str(p["id"]) == sel[0]), None)

    def _selected_downed(self) -> Optional[Dict]:
        sel = self.cap_tree.selection()
        if not sel:
            return None
        return next((d for d in self.downed if str(d["id"]) == sel[0]), None)

    def _update_buttons(self) -> None:
        p = self._selected()
        self.revive_btn["state"] = "normal" if (p and p["revivable"]) else "disabled"
        d = self._selected_downed()
        self.capture_btn["state"] = "normal" if (d and d["capturable"]) else "disabled"

    def _capture(self) -> None:
        d = self._selected_downed()
        if not d or not d["capturable"] or self.career is None:
            return
        if not messagebox.askyesno(self.t["title"], self.t["capture_confirm"].format(name=d["name"], date=d["date"])):
            return
        try:
            backup = self.career.capture(d["id"])
        except sqlite3.OperationalError:
            messagebox.showerror(self.t["title"], self.t["locked"])
            return
        except Exception as exc:          # noqa: BLE001 - shown to the user, not hidden
            messagebox.showerror(self.t["title"], self.t["failed"].format(error=exc))
            return
        self.status.set(self.t["captured_done"].format(name=d["name"], backup=backup))
        self._select_career()

    # -- actions -------------------------------------------------------------------

    def _revive(self) -> None:
        p = self._selected()
        if not p or not p["revivable"] or self.career is None:
            return
        if not messagebox.askyesno(self.t["title"], self.t["revive_confirm"].format(name=p["name"])):
            return
        try:
            backup = self.career.revive(p["id"], self.plane_var.get())
        except sqlite3.OperationalError:
            messagebox.showerror(self.t["title"], self.t["locked"])
            return
        except Exception as exc:          # noqa: BLE001 - shown to the user, not hidden
            messagebox.showerror(self.t["title"], self.t["failed"].format(error=exc))
            return
        self.status.set(self.t["revived"].format(name=p["name"], backup=backup))
        self._select_career()

    # -- flight time ---------------------------------------------------------------------

    def _fill_times(self) -> None:
        self.ft_tree.delete(*self.ft_tree.get_children())
        for w in self.aw_frame.winfo_children():
            w.destroy()
        if self.career is None:
            return
        data = self.career.corrections()
        entries = (data or {}).get("missions", {})
        self.auto_label.configure(text=self.t["auto_on"] if (data or {}).get("auto") else self.t["auto_off"])
        for key in sorted(entries, key=int):
            e = entries[key]
            self.ft_tree.insert("", "end", iid=key,
                                tags=("odd",) if len(self.ft_tree.get_children()) % 2 else (),
                                values=(
                f"{key}  {e.get('date', '')}",
                f"{e['flown_s'] / 60:.0f} min", f"{e['planned_s'] / 60:.0f} min",
                self.t["src_log"] if e.get("source") == "log" else self.t["src_plan"],
                self.t["applied"] if e.get("applied") else self.t["not_applied"]))
        # Awards granted since an apply, offered for withdrawal.
        try:
            since = (corrections.awards_since_apply(self.career.path, data, find_game_dir())
                     if data else [])
        except sqlite3.Error:
            since = []
        if since:
            ttk.Label(self.aw_frame, text=self.t["awards_since"], wraplength=700).pack(anchor="w")
            self.aw_vars = []
            for a in since:
                v = tk.BooleanVar(value=False)
                ttk.Checkbutton(
                    self.aw_frame, variable=v,
                    text=f"{a['who'] or self.t['the_squadron']}  ·  "
                         f"{a['award']}  ·  {a['earnedDate']}"
                ).pack(anchor="w")
                self.aw_vars.append((a["id"], v))
            ttk.Button(self.aw_frame, text=self.t["withdraw"], command=self._withdraw).pack(anchor="e", pady=4)

    def _compute_times(self) -> None:
        if self.career is None:
            return
        game = find_game_dir()
        if game is None:
            self.status.set(self.t["no_game"])
            return
        try:
            data = self.career.compute_corrections(game)
        except Exception as exc:          # noqa: BLE001
            messagebox.showerror(self.t["title"], self.t["failed"].format(error=exc))
            return
        n = len(data.get("missions", {}))
        self.status.set(self.t["computed"].format(n=n) if n else self.t["no_times"])
        self._fill_times()

    def _ft_selected(self, want_applied: bool, everything: bool = False):
        """Mission keys in the wanted state: the selection, or all of them -
        apply and restore always take all, so a career is never half done."""
        data = self.career.corrections() if self.career else None
        entries = (data or {}).get("missions", {})
        keys = list(entries) if everything else (list(self.ft_tree.selection()) or list(entries))
        return [k for k in keys if bool(entries.get(k, {}).get("applied")) == want_applied]

    def _apply_hours(self) -> None:
        keys = self._ft_selected(want_applied=False, everything=True)
        if not keys or not messagebox.askyesno(self.t["title"], self.t["apply_confirm"].format(n=len(keys))):
            return
        try:
            backup, done = self.career.apply_hours()
        except sqlite3.OperationalError:
            messagebox.showerror(self.t["title"], self.t["locked"])
            return
        except Exception as exc:          # noqa: BLE001
            messagebox.showerror(self.t["title"], self.t["failed"].format(error=exc))
            return
        self.status.set(self.t["applied_done"].format(n=len(done), backup=backup))
        self._fill_times()

    def _restore_hours(self) -> None:
        keys = self._ft_selected(want_applied=True, everything=True)
        if not keys:
            return
        game = find_game_dir()
        try:
            due = self.career.hour_awards(game)
        except sqlite3.Error:
            due = []
        text = self.t["restore_confirm"].format(n=len(keys))
        if due:
            text += "\n\n" + self.t["restore_awards"].format(m=len(due)) + "\n" + "\n".join(
                f"  #{a['id']}  pilot {a['pilotId']}  award {a['type']}  {a['earnedDate']}" for a in due)
        if not messagebox.askyesno(self.t["title"], text):
            return
        try:
            backup, done, withdrawn = self.career.restore_hours(game)
        except sqlite3.OperationalError:
            messagebox.showerror(self.t["title"], self.t["locked"])
            return
        except Exception as exc:          # noqa: BLE001
            messagebox.showerror(self.t["title"], self.t["failed"].format(error=exc))
            return
        self.status.set(self.t["restored_done"].format(n=len(done), backup=backup) +
                        ("  " + self.t["restore_awards_done"].format(m=len(withdrawn)) if withdrawn else ""))
        self._fill_times()

    def _withdraw(self) -> None:
        ids = [aid for aid, v in getattr(self, "aw_vars", []) if v.get()]
        if not ids or self.career is None:
            return
        try:
            backup = self.career.backup()
            for aid in ids:
                corrections.withdraw_award(self.career.path, aid)
        except sqlite3.OperationalError:
            messagebox.showerror(self.t["title"], self.t["locked"])
            return
        except Exception as exc:          # noqa: BLE001
            messagebox.showerror(self.t["title"], self.t["failed"].format(error=exc))
            return
        self.status.set(self.t["withdrawn"].format(n=len(ids), backup=backup))
        self._fill_times()

    # -- pending awards ----------------------------------------------------

    def _fill_pending(self) -> None:
        self.pend_tree.delete(*self.pend_tree.get_children())
        self.pending = [] if self.career is None else self.career.pending_awards(find_game_dir())
        # What every man on the list stands at now. Read once, before
        # anything is presented, so the pair of columns has a left-hand side.
        self.pend_before = ({} if self.career is None
                            else self.career.attributes({a["pilot"] for a in self.pending}))
        self.pend_after: Dict[int, tuple] = {}
        # everyone ticked but the dead - those are opted in, not out
        self.pend_checked = {a["id"] for a in self.pending
                             if a["status"] not in ("kia", "mia")}
        for n, a in enumerate(self.pending):
            tags = (("gone",) if a["status"] in ("kia", "mia") else ()) + (("odd",) if n % 2 else ())
            self.pend_tree.insert("", "end", iid=str(a["id"]), tags=tags, values=())
        self._mark_pending()

    def _mark_pending(self) -> None:
        """Redraw the ticks and the running cost."""
        for a in self.pending:
            on = a["id"] in self.pend_checked
            before = self.pend_before.get(a["pilot"])
            after = self.pend_after.get(a["pilot"])
            cells = []
            for n in range(3):
                cells.append("" if before is None else str(before[n]))
                # Blank until the awards are presented; then the new value,
                # with an arrow only where it actually moved.
                if after is None or before is None:
                    cells.append("")
                else:
                    cells.append(("↑ " if after[n] > before[n] else "") + str(after[n]))
            self.pend_tree.item(str(a["id"]), values=(
                ("✓  " if on else "   ") + a["who"],
                self.t["st_" + a["status"]], a["award"], a["earned"], *cells))
        cost = sum(a["cost"] for a in self.pending if a["id"] in self.pend_checked)
        points = self.career.award_points() if self.career else 0
        self.pend_var.set(self.t["pend_cost"].format(n=len(self.pend_checked),
                                                     cost=cost, points=points))
        self.pend_btn.state(["!disabled"] if self.pend_checked and cost <= points
                            else ["disabled"])

    def _toggle_pending(self, event) -> None:
        row = self.pend_tree.identify_row(event.y)
        if not row:
            return
        rid = int(row)
        self.pend_checked.symmetric_difference_update({rid})
        self._mark_pending()

    def _check_pending(self, on: bool) -> None:
        # "All" means every man on strength; the dead stay a deliberate choice
        self.pend_checked = ({a["id"] for a in self.pending
                              if a["status"] not in ("kia", "mia")} if on else set())
        self._mark_pending()

    def _grant_pending(self) -> None:
        if self.career is None or not self.pend_checked:
            return
        try:
            done = self.career.present_awards(sorted(self.pend_checked))
        except ValueError as short:
            need, have = str(short).split("/")
            messagebox.showwarning(self.t["title"],
                                   self.t["pend_short"].format(need=need, points=have))
            return
        except sqlite3.OperationalError:
            messagebox.showerror(self.t["title"], self.t["locked"])
            return
        except Exception as exc:          # noqa: BLE001
            messagebox.showerror(self.t["title"], self.t["failed"].format(error=exc))
            return
        points = self.career.award_points()
        self.points_var.set(self.t["points_now"].format(points=points))
        self.status.set(self.t["pend_done"].format(n=done["granted"], spent=done["spent"],
                                                   backup=done["backup"]))
        # The rows stay up with both sides filled in, so the reader can see
        # what the ceremony moved. They clear on the next refresh or when
        # another career is chosen - by then the awards are history.
        self.pend_after = self.career.attributes(set(self.pend_before))
        self.pend_checked = set()
        self._mark_pending()
        self.pend_btn.state(["disabled"])

    # -- flights ---------------------------------------------------------------

    def _build_board(self, board: tk.Frame, groups: List[Group]) -> None:
        """
        The line-up, laid out the way its air force organises it.

        An American squadron is six flights of four in one row. An eastern
        regiment is a commander pair and three squadrons of twelve, two
        squadrons to a row - six columns instead of ten. The game sets all
        of them side by side and scrolls sideways to reach the far ones;
        two rows needs no sideways scrolling.

        Rebuilt whenever a career with a different shape is chosen, which
        is why the cards are cleared here rather than kept.
        """
        for child in board.winfo_children():
            child.destroy()
        self.fl_cards.clear()
        self.fl_heads.clear()
        for n, g in enumerate(groups):
            # Two grid rows per board row: the squadron's name, then its
            # flights. The name spans the row because a column headed
            # "Flight 1" means nothing until you know whose flight it is.
            if g.row_label:
                # Spans its own squadron's three columns, not the whole row -
                # there are two squadrons side by side on it.
                tk.Label(board, text=g.row_label, background=self.PANEL,
                         foreground=self.ACCENT, font=("Georgia", 11, "bold"),
                         anchor="w", pady=2).grid(row=g.row * 2, column=g.col,
                                                  columnspan=3, sticky="w", padx=4)
            col = tk.Frame(board, background=self.PANEL)
            col.grid(row=g.row * 2 + 1, column=g.col, padx=2, pady=(0, 6), sticky="n")
            head = tk.Label(col, text=g.label, background=self.DESK,
                            foreground=self.ACCENT_DARK, font=("Georgia", 10, "bold"),
                            width=17, pady=4)
            head.pack(fill="x")
            self.fl_heads[n] = head
            for pos in range(g.size):
                if pos and pos % 2 == 0:          # the section rule
                    tk.Frame(col, background=self.BORDER, height=1).pack(fill="x", pady=2)
                slot = g.start + pos
                card = tk.Frame(col, background=self.PAPER, padx=4, pady=2,
                                highlightthickness=1, highlightbackground=self.BORDER)
                card.pack(fill="x", pady=1)
                who = tk.Label(card, background=self.PAPER, anchor="w", width=15,
                               font=("Georgia", 11, "bold"))
                line = tk.Label(card, background=self.PAPER, anchor="w",
                                font=("Georgia", 10), foreground=self.INK)
                stat = tk.Label(card, background=self.PAPER, anchor="w",
                                font=("", 9), foreground=self.INK_MUTED)
                note = tk.Label(card, background=self.PAPER, anchor="w",
                                font=("", 9), foreground=self.ACCENT)
                for widget in (who, line, stat, note):
                    widget.pack(fill="x")
                self.fl_cards[slot] = (card, who, line, stat, note)
                for widget in (card, who, line, stat, note):
                    widget.bind("<Button-1>", lambda _e, s=slot: self._pick_seat(s))

    def _fill_flights(self) -> None:
        """Read the line-up and the bench back from the career and draw them."""
        self.fl_pick = self.fl_up = None
        # This career's line-up may be a different size, or a different
        # shape: an American squadron and an eastern regiment are not the
        # same board with more cards on it.
        if self.career is None:
            seats, country = Career.SEATS, 601
        else:
            seats, country = self.career.seats(), self.career.country()
        groups = line_up_shape(country, seats, self.t, self.game_t)
        if [g[1:] for g in groups] != [g[1:] for g in self.fl_groups]:
            self.fl_groups = groups
            self.fl_seats = seats
            self._build_board(self.fl_board, groups)
        else:
            self.fl_groups = groups
        self.fl_men, self.fl_plan = {}, {s: None for s in range(seats)}
        if self.career is None:
            self._draw_seats()
            self._fill_bench()
            return
        try:
            seats = self.career.flight_seats()
            bench = self.career.pool_pilots()
        except sqlite3.Error as exc:
            self.status.set(self.t["failed"].format(error=exc))
            return
        self.fl_alert = {s["slot"] for s in seats if s["alert"]}
        for seat in seats:
            man = seat["pilot"]
            self.fl_plan[seat["slot"]] = man["id"] if man else None
            if man:
                self.fl_men[man["id"]] = man
        for man in bench:
            self.fl_men[man["id"]] = man
        self.fl_var.set(self.t["fl_hint"] if self.fl_men else self.t["fl_none"])
        self._draw_seats()
        self._fill_bench()

    def _fill_bench(self) -> None:
        """Everyone the plan does not seat, which is the reserve as it would
        stand if the plan were applied."""
        self.bench_tree.delete(*self.bench_tree.get_children())
        seated = {pid for pid in self.fl_plan.values() if pid is not None}
        bench = sorted((m for i, m in self.fl_men.items() if i not in seated),
                       key=lambda m: (-m["ai"], m["home"]))
        for n, man in enumerate(bench):
            tags = ["odd"] if n % 2 else []
            if not man["available"]:
                tags.append("gone")
            self.bench_tree.insert(
                "", "end", iid=str(man["id"]), tags=tuple(tags), values=(
                    man["who"],
                    f"{man['sk'] + 1}/{man['di'] + 1}/{man['co'] + 1}",
                    man["ai"],
                    "/".join(str(b) for b in man["boost"]),
                    self.t["st_" + Career._pilot_status(man["state"], man["home"])]))

    def _pick_bench(self, _event=None) -> None:
        """Take a man off the bench; the next seat clicked exchanges him."""
        sel = self.bench_tree.selection()
        self.fl_up = int(sel[0]) if sel else None
        if self.fl_up is not None:
            self.fl_pick = None
            self._draw_seats()

    def _draw_seats(self) -> None:
        """
        Repaint every card from the plan. A moved man gets the stripe, and a
        seat on alert gets the duty edge - which flight that is comes from
        squadron.watchmen, since the player can put the D flight anywhere.
        """
        self.fl_lead_seats = {g.start for g in self.fl_groups}
        for n, head in self.fl_heads.items():
            g = self.fl_groups[n]
            block = set(range(g.start, g.start + g.size))
            title = g.label
            # The duty group is four consecutive seats and need not line up
            # with a block: in a Chinese regiment it was slots 16-19, the
            # back half of one flight and the front half of the next. So the
            # heading is marked when any of its seats are on duty, and the
            # seats themselves carry the edge.
            if block & self.fl_alert:
                title += "  " + self.t["fl_alert"]
            head.configure(text=title)
        for slot, (card, who, line, stat, note) in self.fl_cards.items():
            man = self.fl_men.get(self.fl_plan.get(slot))
            moved = man is not None and man["home"] != slot
            picked = slot == self.fl_pick
            back = self.STRIPE if moved else self.PAPER
            edge = self.BORDER
            if slot in self.fl_alert:
                edge = self.DUTY
            if picked:
                edge = self.ACCENT
            card.configure(background=back, highlightthickness=2 if picked else 1,
                           highlightbackground=edge)
            for widget in (who, line, stat, note):
                widget.configure(background=back)
            # A lead is the first seat of its own block. slot % 4 is only
            # that when blocks begin at 0, 4, 8 - an eastern regiment's
            # flights begin at 2, 6, 10, which put the star on the third
            # card of every flight.
            lead = slot in self.fl_lead_seats
            if man is None:
                who.configure(text=self.t["fl_empty"], foreground="#a3947c")
                line.configure(text="")
                stat.configure(text="")
                note.configure(text="\u2605" if lead else "")
                continue
            who.configure(text=man["short"],
                          foreground=self.BAD if not man["available"] else self.INK)
            # the three attributes as the pilot's own panel prints them:
            # skills, discipline, courage, each stored one lower than shown.
            # The commander has none - the game simulates no skill for a man
            # a human flies - so he gets his tail number alone.
            if man["player"]:
                line.configure(text=man["tail"])
            else:
                line.configure(text=f"{man['tail']}   "
                                    f"{man['sk'] + 1}/{man['di'] + 1}/{man['co'] + 1}")
            bits = []
            if not man["player"]:
                bits.append(f"{self.t['fl_ai']} {man['ai']}")
            if not man["available"]:
                bits.append(self.t["st_" + Career._pilot_status(
                    man["state"], man["home"])])
            stat.configure(
                text=" \u00b7 ".join(bits),
                foreground=self.BAD if not man["available"] else self.INK_MUTED)
            # the boosters in the panel's order, the way the mission screen
            # prints the commander's three chips
            tag = "\u2191" + "/".join(str(b) for b in man["boost"]) if any(man["boost"]) else ""
            if lead:
                tag = ("\u2605 " + tag).strip()
            if man["player"]:
                tag = (tag + " " + self.t["fl_you"]).strip()
            note.configure(text=tag)

    def _pick_seat(self, slot: int) -> None:
        """First click takes a pilot, second click puts him in that seat."""
        if not self.fl_men:
            return
        if self.fl_up is not None:
            # a man off the bench takes the seat and its aeroplane, and the
            # man he replaces goes down. An empty seat has no aircraft to
            # inherit, so it cannot take him.
            coming = self.fl_men.get(self.fl_up)
            if coming is not None and not coming["available"]:
                self.status.set(self.t["fl_unavailable"].format(
                    who=coming["who"],
                    state=self.t["st_" + Career._pilot_status(
                        coming["state"], coming["home"])]))
                return
            if self.fl_plan.get(slot) is None:
                return
            self.fl_plan[slot] = self.fl_up
            self.fl_up = None
            self.bench_tree.selection_remove(*self.bench_tree.selection())
            self.fl_var.set(self.t["fl_moved"].format(n=self._moved_count()))
            self._draw_seats()
            self._fill_bench()
            return
        if self.fl_pick is None:
            if self.fl_plan.get(slot) is None:
                return                       # an empty seat cannot start a swap
            self.fl_pick = slot
        elif self.fl_pick == slot:
            self.fl_pick = None              # clicked again: put him back down
        else:
            first, second = self.fl_pick, slot
            self.fl_plan[first], self.fl_plan[second] = (
                self.fl_plan.get(second), self.fl_plan.get(first))
            self.fl_pick = None
            self.fl_var.set(self.t["fl_moved"].format(n=self._moved_count()))
        self._draw_seats()
        self._fill_bench()

    def _moved_count(self) -> int:
        return sum(1 for slot, pid in self.fl_plan.items()
                   if pid is not None and self.fl_men[pid]["home"] != slot)

    def _propose_seats(self) -> None:
        """
        Lay out a fresh proposal from the career as it stands on disk, not
        from whatever the board has been dragged into - otherwise a half-made
        arrangement quietly steers the next suggestion.
        """
        if self.career is None:
            return
        try:
            seats = self.career.flight_seats()
        except sqlite3.Error as exc:
            self.status.set(self.t["failed"].format(error=exc))
            return
        bench = self.career.pool_pilots()
        self.fl_men = {s["pilot"]["id"]: s["pilot"] for s in seats if s["pilot"]}
        for man in bench:
            self.fl_men[man["id"]] = man
        if not self.fl_men:
            self.fl_var.set(self.t["fl_none"])
            return
        self.fl_plan = {s: None for s in range(self.fl_seats)}
        self.fl_plan.update(
            propose_seating(seats, bench if self.fl_pool_var.get() else None))
        self.fl_pick = self.fl_up = None
        self.fl_var.set(self.t["fl_moved"].format(n=self._moved_count()))
        self._draw_seats()
        self._fill_bench()

    def _apply_seats(self) -> None:
        if self.career is None or not self.fl_men:
            return
        moved = self._moved_count()
        if not moved:
            self.status.set(self.t["fl_nochange"])
            return
        plan = {slot: pid for slot, pid in self.fl_plan.items() if pid is not None}
        try:
            backup = self.career.reseat(plan)
        except sqlite3.OperationalError:
            self.status.set(self.t["locked"])
            return
        except (sqlite3.Error, ValueError) as exc:
            self.status.set(self.t["failed"].format(error=exc))
            return
        self.status.set(self.t["fl_applied"].format(n=moved, backup=backup.name))
        self._fill_flights()

    def _add_points(self) -> None:
        if self.career is None:
            return
        try:
            amount = int(self.amount.get())
        except (tk.TclError, ValueError):
            return
        if amount <= 0:
            return
        try:
            backup = self.career.add_points(amount)
            points = self.career.award_points()
        except sqlite3.OperationalError:
            messagebox.showerror(self.t["title"], self.t["locked"])
            return
        except Exception as exc:          # noqa: BLE001
            messagebox.showerror(self.t["title"], self.t["failed"].format(error=exc))
            return
        self.points_var.set(self.t["points_now"].format(points=points))
        self.status.set(self.t["points_added"].format(points=points, backup=backup))
        self._mark_pending()          # the pool moved, so the button may open


MOD_MARKER = b"[Award=601042]"     # the Distinguished Unit Citation: only the awards mod defines it


def mod_installed(game: Optional[Path]) -> bool:
    """The awards mod's live awards.cfg is in the game folder."""
    if game is None:
        return False
    cfg = game / "data" / "scg" / "2" / "awards.cfg"
    try:
        return MOD_MARKER in cfg.read_bytes()
    except OSError:
        return False


def main() -> int:
    # Build/diagnostic probe: exercise the same bundled model, background and
    # texconv executable that the UI uses, without touching a career. The
    # windowed executable has no console, so success is the validated DDS at
    # the requested output path.
    if "--photo-self-test" in sys.argv:
        at = sys.argv.index("--photo-self-test")
        try:
            source = pilot_photo.load_photo(Path(sys.argv[at + 1]))
            if not pilot_photo.has_useful_alpha(source):
                source = pilot_photo.remove_background(source)
            with Image.open(pilot_photo.background_path()) as background:
                composed = pilot_photo.compose_portrait(source, background)
            pilot_photo.convert_to_dds(composed, Path(sys.argv[at + 2]))
            return 0
        except Exception:                 # windowed diagnostic reports by exit status
            return 4

    # Meant to be opened from the Service Record, and only where the awards
    # mod is installed: award points buy decorations the mod adds, revival
    # and re-timing belong with it. Neither check is a lock - both are a
    # polite door, so the helper is not used as a bare cheat tool.
    t = STRINGS[pick_language()]
    root = tk.Tk(); root.withdraw()
    if "--from-tracker" not in sys.argv:
        messagebox.showinfo(t["title"], t["open_from_tracker"])
        return 2
    if not mod_installed(find_game_dir()):
        messagebox.showinfo(t["title"], t["needs_mod"])
        return 3
    root.destroy()
    app = App()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
