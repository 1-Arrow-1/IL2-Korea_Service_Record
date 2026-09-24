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

import locale
import sqlite3
import urllib.parse
from datetime import datetime
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from korea_service_record.locate import find_game_dir          # noqa: E402
from korea_service_record.settings import Settings             # noqa: E402
from korea_service_record.assets import default_cache_dir      # noqa: E402
from korea_service_record import corrections                   # noqa: E402

BACKUPS = default_cache_dir().parent / "backups"
LINEUP = range(0, 20)          # squadron line-up slots
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
        "fl_fat": "fatigue",
        "fl_hurt": "hurt",
        "fl_rest": "needs rest",
        "fl_b_boost": "Boosters",
        "fl_b_stats": "S/D/C",
        "fl_use_pool": "let the proposal draw on the reserve",
        "fl_bench_hint": "Pick a man here, then click a seat: he takes it and its aircraft, and the man he replaces goes down to the pool. One for one.",
        "fl_bench": "Reserve pool",
        "fl_none": "This career has no line-up to show.",
        "fl_moved": "{n} moved",
        "fl_legend": "The three numbers are the pilot's own skills / discipline / courage, as his panel shows them. ↑ is his boosters. AI is how the generated mission rates him in the air: his skill, but capped at 4 - so a pilot at 5 flies no better than one at 4, and a wound costs him a level. Fatigue runs to 9: a sortie adds one, a day on the ground takes one back.",
        "col_name": "Pilot", "col_state": "Fate", "col_date": "Lost on", "col_can": "Revivable",
        "kia": "killed in action", "mia": "missing in action",
        "yes": "yes", "no": "no - the career has moved on",
        "no_dead": "Nobody has been lost in this career.",
        "restore_plane": "Restore his aircraft too (otherwise: bailed out, aircraft lost)",
        "revive": "Revive",
        "revive_confirm": "Bring {name} back into the line-up?",
        "revived": "{name} is back in the line-up. Backup: {backup}",
        "rule": "A pilot can only be revived while the career is still on the day he was lost. Today is {date}.",
        "points_now": "The squadron's award points now: {points}",
        "points_add": "Add",
        "points_added": "Award points are now {points}. Backup: {backup}",
        "pending_intro": "Awards your pilots have earned but not yet been given. Each costs one award point. Click a line to include or exclude it, then hand them over.",
        "pend_col_who": "Pilot",
        "pend_col_award": "Award",
        "pend_col_earned": "Earned",
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
        "fl_fat": "Ermüdung",
        "fl_hurt": "verwundet",
        "fl_rest": "braucht Ruhe",
        "fl_b_boost": "Boni",
        "fl_b_stats": "F/D/M",
        "fl_use_pool": "Reserve in den Vorschlag einbeziehen",
        "fl_bench_hint": "Hier einen Mann wählen, dann einen Platz anklicken: Er übernimmt Platz und Maschine, der Abgelöste geht in die Reserve. Einer für einen.",
        "fl_bench": "Reserve",
        "fl_none": "Diese Laufbahn hat keine Staffelaufstellung.",
        "fl_moved": "{n} versetzt",
        "fl_legend": "Die drei Zahlen sind die eigenen Werte des Piloten – Fähigkeiten / Disziplin / Mut – so wie sie sein Blatt zeigt. ↑ sind seine Boni. KI ist die Einstufung, die der erzeugte Einsatz ihm in der Luft gibt: seine Fähigkeiten, aber bei 4 gedeckelt – ein Pilot mit 5 fliegt also nicht besser als einer mit 4, und eine Verwundung kostet ihn eine Stufe. Die Ermüdung reicht bis 9: ein Einsatz bringt einen Punkt, ein Tag am Boden nimmt einen zurück.",
        "col_name": "Pilot", "col_state": "Schicksal", "col_date": "Verloren am", "col_can": "Zurückholbar",
        "kia": "gefallen", "mia": "vermisst",
        "yes": "ja", "no": "nein - die Laufbahn ist weitergegangen",
        "no_dead": "In dieser Laufbahn ist niemand verloren gegangen.",
        "restore_plane": "Auch sein Flugzeug wiederherstellen (sonst: abgesprungen, Flugzeug verloren)",
        "revive": "Zurückholen",
        "revive_confirm": "{name} wieder in die Aufstellung nehmen?",
        "revived": "{name} ist zurück in der Aufstellung. Sicherung: {backup}",
        "rule": "Ein Pilot kann nur zurückgeholt werden, solange die Laufbahn noch auf dem Tag seines Verlusts steht. Heute ist der {date}.",
        "points_now": "Auszeichnungspunkte der Staffel: {points}",
        "points_add": "Hinzufügen",
        "points_added": "Die Auszeichnungspunkte betragen jetzt {points}. Sicherung: {backup}",
        "pending_intro": "Auszeichnungen, die Ihre Piloten erhalten haben, aber noch nicht verliehen bekamen. Jede kostet einen Auszeichnungspunkt. Klicken Sie eine Zeile an, um sie ein- oder auszuschließen, und verleihen Sie sie dann.",
        "pend_col_who": "Pilot",
        "pend_col_award": "Auszeichnung",
        "pend_col_earned": "Erworben",
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
        "fl_fat": "fatiga",
        "fl_hurt": "herido",
        "fl_rest": "necesita descanso",
        "fl_b_boost": "Bonif.",
        "fl_b_stats": "H/D/V",
        "fl_use_pool": "que la propuesta recurra a la reserva",
        "fl_bench_hint": "Elija aquí a un piloto y pulse un puesto: ocupa el puesto y su avión, y el sustituido pasa a la reserva. Uno por uno.",
        "fl_bench": "Reserva",
        "fl_none": "Esta carrera no tiene formación que mostrar.",
        "fl_moved": "{n} movidos",
        "fl_legend": "Los tres números son las aptitudes propias del piloto: habilidad / disciplina / valor, tal como aparecen en su ficha. ↑ son sus bonificaciones. IA es la categoría que la misión generada le asigna en vuelo: su habilidad, pero limitada a 4, de modo que un piloto de 5 no vuela mejor que uno de 4, y una herida le cuesta un nivel. La fatiga llega a 9: una salida suma uno y un día en tierra descuenta uno.",
        "col_name": "Piloto", "col_state": "Suerte", "col_date": "Perdido el", "col_can": "Recuperable",
        "kia": "muerto en combate", "mia": "desaparecido en combate",
        "yes": "sí", "no": "no: la carrera ya ha avanzado",
        "no_dead": "Nadie se ha perdido en esta carrera.",
        "restore_plane": "Restaurar también su avión (si no: saltó en paracaídas, avión perdido)",
        "revive": "Recuperar",
        "revive_confirm": "¿Devolver a {name} a la alineación?",
        "revived": "{name} vuelve a estar en la alineación. Copia de seguridad: {backup}",
        "rule": "Un piloto solo puede recuperarse mientras la carrera siga en el día en que se perdió. Hoy es {date}.",
        "points_now": "Puntos de condecoración del escuadrón: {points}",
        "points_add": "Añadir",
        "points_added": "Los puntos de condecoración son ahora {points}. Copia de seguridad: {backup}",
        "pending_intro": "Condecoraciones que sus pilotos han ganado pero aún no han recibido. Cada una cuesta un punto. Pulse una línea para incluirla o excluirla y después entréguelas.",
        "pend_col_who": "Piloto",
        "pend_col_award": "Condecoración",
        "pend_col_earned": "Ganada",
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
        "fl_fat": "fatigue",
        "fl_hurt": "blessé",
        "fl_rest": "doit se reposer",
        "fl_b_boost": "Bonus",
        "fl_b_stats": "C/D/C",
        "fl_use_pool": "autoriser la proposition à puiser dans la réserve",
        "fl_bench_hint": "Choisissez un pilote ici, puis cliquez sur une place : il la prend avec son appareil, et celui qu’il remplace passe en réserve. Un pour un.",
        "fl_bench": "Réserve",
        "fl_none": "Cette carrière n’a aucune formation à afficher.",
        "fl_moved": "{n} déplacés",
        "fl_legend": "Les trois nombres sont les qualités propres du pilote — compétence / discipline / courage — telles que sa fiche les affiche. ↑ ce sont ses bonus. IA est le niveau que la mission générée lui donne en vol : sa compétence, mais plafonnée à 4, si bien qu’un pilote à 5 ne vole pas mieux qu’un pilote à 4, et une blessure lui coûte un niveau. La fatigue monte jusqu’à 9 : une sortie en ajoute un, une journée au sol en retire un.",
        "col_name": "Pilote", "col_state": "Sort", "col_date": "Perdu le", "col_can": "Récupérable",
        "kia": "mort au combat", "mia": "porté disparu",
        "yes": "oui", "no": "non - la carrière a continué",
        "no_dead": "Personne n’a été perdu dans cette carrière.",
        "restore_plane": "Rétablir aussi son avion (sinon : sauté en parachute, avion perdu)",
        "revive": "Ramener",
        "revive_confirm": "Remettre {name} dans l’ordre de bataille ?",
        "revived": "{name} est de retour dans l’ordre de bataille. Sauvegarde : {backup}",
        "rule": "Un pilote ne peut être ramené que tant que la carrière est encore au jour de sa perte. Nous sommes le {date}.",
        "points_now": "Points de décoration de l’escadron : {points}",
        "points_add": "Ajouter",
        "points_added": "Les points de décoration sont maintenant à {points}. Sauvegarde : {backup}",
        "pending_intro": "Décorations que vos pilotes ont méritées mais pas encore reçues. Chacune coûte un point. Cliquez sur une ligne pour l’inclure ou l’exclure, puis remettez-les.",
        "pend_col_who": "Pilote",
        "pend_col_award": "Décoration",
        "pend_col_earned": "Méritée",
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
        "fl_fat": "усталость",
        "fl_hurt": "ранен",
        "fl_rest": "нужен отдых",
        "fl_b_boost": "Надбавки",
        "fl_b_stats": "М/Д/С",
        "fl_use_pool": "разрешить брать людей из резерва",
        "fl_bench_hint": "Выберите здесь лётчика, затем щёлкните по месту: он занимает его вместе с самолётом, а тот, кого он сменил, уходит в резерв. Один на одного.",
        "fl_bench": "Резерв",
        "fl_none": "В этой карьере нет строевого состава.",
        "fl_moved": "переставлено: {n}",
        "fl_legend": "Три числа — собственные качества лётчика: мастерство / дисциплина / смелость, в том же порядке, что и в его карточке. ↑ — его надбавки. ИИ — оценка, которую сгенерированный вылет даёт ему в воздухе: его мастерство, но не выше 4 — так что лётчик с 5 летает не лучше, чем с 4, а ранение стоит ему одной ступени. Усталость доходит до 9: вылет добавляет единицу, день на земле снимает её.",
        "col_name": "Лётчик", "col_state": "Судьба", "col_date": "Потерян", "col_can": "Можно вернуть",
        "kia": "погиб", "mia": "пропал без вести",
        "yes": "да", "no": "нет — карьера ушла дальше",
        "no_dead": "В этой карьере никто не потерян.",
        "restore_plane": "Вернуть и его самолёт (иначе: выпрыгнул с парашютом, самолёт потерян)",
        "revive": "Вернуть",
        "revive_confirm": "Вернуть {name} в строй?",
        "revived": "{name} снова в строю. Резервная копия: {backup}",
        "rule": "Лётчика можно вернуть, только пока карьера ещё стоит на дне его потери. Сегодня {date}.",
        "points_now": "Наградные очки эскадрильи: {points}",
        "points_add": "Добавить",
        "points_added": "Наградных очков теперь {points}. Резервная копия: {backup}",
        "pending_intro": "Награды, заслуженные вашими лётчиками, но ещё не вручённые. Каждая стоит одно наградное очко. Щёлкните по строке, чтобы включить или исключить её, затем вручите.",
        "pend_col_who": "Лётчик",
        "pend_col_award": "Награда",
        "pend_col_earned": "Заслужена",
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
        "fl_fat": "疲劳",
        "fl_hurt": "负伤",
        "fl_rest": "需要休整",
        "fl_b_boost": "加成",
        "fl_b_stats": "技/律/勇",
        "fl_use_pool": "允许建议编排动用预备队",
        "fl_bench_hint": "在此选中一名飞行员，再点击一个位置：他接手该位置及其座机，被替下的人进入预备队。一换一。",
        "fl_bench": "预备队",
        "fl_none": "该生涯没有可显示的编队。",
        "fl_moved": "已移动 {n} 人",
        "fl_legend": "三个数字是飞行员自身的技能 / 纪律 / 勇气，与他的面板显示一致。↑ 是他的加成。AI 是生成的任务对他空中表现的评级：取决于技能，但上限为 4 —— 所以技能 5 的飞行员并不比 4 的飞得好，而负伤会降一级。 疲劳最高为 9：每出击一次加一点，每在地面休整一天减一点。",
        "col_name": "飞行员", "col_state": "结局", "col_date": "损失日期", "col_can": "可复活",
        "kia": "阵亡", "mia": "失踪",
        "yes": "是", "no": "否——生涯已进入下一天",
        "no_dead": "此生涯中无人损失。",
        "restore_plane": "同时恢复他的飞机（否则：跳伞，飞机损失）",
        "revive": "复活",
        "revive_confirm": "让 {name} 重返编队？",
        "revived": "{name} 已重返编队。备份：{backup}",
        "rule": "只有当生涯仍停留在飞行员损失当天时才能复活。今天是 {date}。",
        "points_now": "中队当前授勋点数：{points}",
        "points_add": "增加",
        "points_added": "授勋点数现为 {points}。备份：{backup}",
        "pending_intro": "您的飞行员已获得但尚未授予的奖励。每项消耗一点授勋点数。点击某行以选中或取消，然后予以授予。",
        "pend_col_who": "飞行员",
        "pend_col_award": "奖励",
        "pend_col_earned": "获得日期",
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
    },
}


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

    def player_ids(self) -> set:
        with self._open() as con:
            ids = {r[0] for r in con.execute("SELECT id FROM pilot WHERE isPlayer=1")}
            ids.add(con.execute("SELECT playerId FROM career").fetchone()[0])
            return ids

    def lost_pilots(self) -> List[Dict]:
        """KIA and MIA pilots, never the player, with whether today is still the day."""
        today = self.current_date()
        players = self.player_ids()
        out = []
        with self._open() as con:
            rows = con.execute(
                "SELECT id, name, lastName, rankId, state, stateDate FROM pilot "
                "WHERE isDeleted=0 AND state IN (2, 3) ORDER BY stateDate DESC, id")
            for r in rows:
                if r["id"] in players:
                    continue
                lost_on = (r["stateDate"] or "")[:10]
                out.append({
                    "id": r["id"],
                    "name": f"{r['name']} {r['lastName']}".strip(),
                    "state": r["state"],
                    "lost_on": lost_on,
                    "revivable": lost_on == today,
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

    def pending_awards(self, game: Optional[Path] = None) -> List[Dict]:
        """
        Every award earned and not yet presented, by pilot.

        Everyone, including the dead: a posthumous award is a real thing
        and the game offers them too. Each line carries the man's standing,
        and the killed and the missing come in unticked and in red, so
        presenting to them is a decision taken rather than one slipped past.
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

        state first, because it outranks the slot: 2 killed, 3 missing,
        4 in hospital, 1 walking home. Then the slot bands - 0..19 the
        line-up, 1000..1999 parked with an aircraft under repair, which the
        Combat units screen calls "in reserve - NOT READY", and 2000..4999
        the replacement pool.
        """
        state, slot = int(state or 0), int(slot or 0)
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
                    FROM award WHERE id IN ({marks}) AND isPending=1 AND isDeleted=0""",
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

    SEATS = 24
    FLIGHTS = 6
    PARK = 9000                          # scratch slots while a permutation lands

    # Fatigue runs 0 to 9. careerProcessor.dll adds one for every sortie a
    # pilot flies, hard-clamped at 9 (FUN_18006b690), and takes one back for
    # every mission day he sits out, floored at 0 - the rollover walks the
    # squadron, looks each man up in the list of those who flew, and decrements
    # everyone it does not find (FUN_18003d460). What a tired pilot actually
    # does worse is not proven: nothing in the DLL reads the field for
    # arithmetic, and it plainly does not reach AILevel, since men at 6 still
    # generate as AI 4. REST is therefore a judgement - two thirds of the
    # scale - and is meant to be argued with.
    FATIGUE_MAX = 9
    FATIGUE_REST = 6
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
            "fatigue": int(row["fatigue"] or 0),
            "health": int(row["health"] or 100),
            "state": int(row["state"] or 0),
            "player": bool(row["isPlayer"]),
            "sorties": int(row["sorties"] or 0),
            "home": slot,
            "tail": tail,
        }
        man["ai"] = self.ai_level(man["sk"], man["health"], man["state"])
        man["hurt"] = man["state"] == 4 or man["health"] < 100
        # the game counts the player's sorties like anyone else's, but how he
        # flies on the day is his business and not the career file's - so he
        # is never told to go and rest
        man["tired"] = man["fatigue"] >= self.FATIGUE_REST and not man["player"]
        return man

    PILOT_COLS = """SELECT id, slot, name, lastName, persLevel, leadLevel, fatigue,
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
        with self._open() as con:
            rows = con.execute(
                f"{self.PILOT_COLS} AND slot>=? AND slot<? ORDER BY slot",
                (self.SEATS, self.RESERVE_TOP)).fetchall()
        return [self._read_man(r, "", r["slot"]) for r in rows]

    def flight_seats(self) -> List[Dict]:
        """All 24 seats in order, each with its pilot and aircraft or None."""
        with self._open() as con:
            men = {r["slot"]: r for r in con.execute(
                f"{self.PILOT_COLS} AND slot<?", (self.SEATS,))}
            planes = {r["slot"]: r for r in con.execute(
                "SELECT id, slot, tcode, state FROM plane WHERE isDeleted=0 AND slot<?",
                (self.SEATS,))}
            row = con.execute("SELECT watchmen FROM squadron").fetchone()
        alert = self.parse_watchmen(row[0] if row else "")
        seats = []
        for slot in range(self.SEATS):
            row, air = men.get(slot), planes.get(slot)
            man = None
            if row is not None:
                man = self._read_man(
                    row, decode_tcode(air["tcode"]) if air is not None else "", slot)
            seats.append({"slot": slot, "flight": slot // 4, "section": slot // 2,
                          "lead": slot % 4 == 0, "alert": slot in alert, "pilot": man,
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
        backup = self.backup()
        with self._open(write=True) as con:
            con.execute("BEGIN IMMEDIATE")
            seated = {r["slot"]: r["id"] for r in con.execute(
                "SELECT id, slot FROM pilot WHERE isDeleted=0 AND slot<?", (self.SEATS,))}
            benched = [r["id"] for r in con.execute(
                """SELECT id FROM pilot WHERE isDeleted=0 AND slot>=? AND slot<?
                   ORDER BY slot""", (self.SEATS, self.RESERVE_TOP))]
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
                "SELECT id, slot FROM plane WHERE isDeleted=0 AND slot<?", (self.SEATS,))}
            home = {pid: slot for slot, pid in seated.items()}
            promoted = [pid for pid in plan.values() if pid not in home]
            demoted = [pid for pid in seated.values() if pid not in set(plan.values())]
            pilot_home = {r["id"]: r["slot"] for r in con.execute(
                """SELECT id, slot FROM pilot WHERE isDeleted=0
                   AND slot>=? AND slot<?""", (self.SEATS, self.RESERVE_TOP))}

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
    def _free_slot(con: sqlite3.Connection) -> int:
        """Lowest free line-up slot, else the lowest free reserve slot."""
        taken = {r[0] for r in con.execute("SELECT slot FROM pilot WHERE isDeleted=0")}
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
            slot = self._free_slot(con)
            con.execute("UPDATE pilot SET state=0, health=100, slot=? WHERE id=?", (slot, pilot_id))
            # The KIA/MIA event of that loss. Retired, not deleted: the game
            # never reads deleted rows, and the row stays for the record.
            con.execute(
                "UPDATE event SET isDeleted=1 WHERE pilotId=? AND type IN (3, 4) AND isDeleted=0 "
                "AND substr(date, 1, 10)=?", (pilot_id, (pilot["stateDate"] or "")[:10]))
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
    terms, one for one: whoever is displaced goes down to the pool. The
    wounded are never brought up.

    Wingmen are seated on what the game reads for them instead: AILevel, which
    comes from skill alone and saturates at 4, then discipline, then rest.
    Filling a tier at a time spreads strength across the flights rather than
    piling it into the first, because missions go out as whole flights. The
    alert seats take neither a wounded nor a worn-out man while a fresh one is
    left, since they are the ones that scramble without warning - and which
    seats those are is read from squadron.watchmen, because the player can
    move the D flight anywhere.

    Two floors apply. Nobody below LEAD_MIN_AI leads a flight or a section
    while a qualified man is free, because boosters are so scarce - nought to
    three across a whole squadron - that ranking on them alone otherwise hands
    a flight to the worst flier in it, and, once the reserve is in play, hands
    a section to a replacement who has never flown. And a man at or past FATIGUE_REST is
    treated as wanting a rest: he is kept off the alert seats and out of the
    lead seats, and his card says so, but he is still seated, because whether
    he actually flies is decided on the mission screen and not here.
    """
    taken = [s for s in seats if s["pilot"]]
    # A benched man is only ever picked when he is strictly better, because
    # the "is he already here" tiebreak can never fire for him - his home is a
    # pool slot, never a seat. So the line-up is left alone unless the reserve
    # genuinely improves it.
    pool = [s["pilot"] for s in taken] + [
        m for m in (bench or []) if not m["hurt"]]
    plan = {}

    player = next((m for m in pool if m["player"]), None)
    if player is not None:                       # the commander keeps his seat
        plan[player["home"]] = player["id"]
        pool.remove(player)

    open_seats = [s["slot"] for s in taken if s["slot"] not in plan]
    tiers = {0: 0, 2: 1}                         # flight lead, section lead, the rest
    open_seats.sort(key=lambda s: (tiers.get(s % 4, 2), s))

    # The trailing "is he already here" term leaves a man where he sits when
    # nothing else separates him from the alternative: a proposal you have to
    # undo by hand is worse than no proposal at all.
    def as_lead(man, slot):
        return (sum(man["boost"]), man["ai"], man["sk"], -man["fatigue"],
                man["home"] == slot)

    def as_wingman(man, slot):
        return (man["ai"], man["di"], -man["fatigue"], man["sk"],
                man["home"] == slot)

    alert = {s["slot"] for s in taken if s.get("alert")}
    for slot in open_seats:
        if not pool:
            break
        take = pool
        if slot in alert:                        # scrambles without warning
            ready = [m for m in take if not m["hurt"] and not m["tired"]]
            take = ready or [m for m in take if not m["hurt"]] or pool
        if slot % 2 == 0:                        # a flight or section lead
            able = [m for m in take if m["ai"] >= Career.LEAD_MIN_AI]
            rested = [m for m in able if not m["tired"]]
            take = rested or able or take
        rank = as_lead if slot % 2 == 0 else as_wingman
        pick = max(take, key=lambda m: rank(m, slot))
        plan[slot] = pick["id"]
        pool.remove(pick)
    return plan


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.t = STRINGS[pick_language()]
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
        self.pend_tree = ttk.Treeview(pts, columns=("who", "status", "award", "earned"),
                                      show="headings", height=9, selectmode="none")
        # The fallen are listed but stand out: a posthumous award is the
        # commander's decision, not something to tick past by accident.
        self.pend_tree.tag_configure("gone", foreground=self.BAD)
        self.pend_tree.tag_configure("odd", background=self.STRIPE)
        for col, w in (("who", 170), ("status", 100), ("award", 300), ("earned", 100)):
            self.pend_tree.heading(col, text=self.t["pend_col_" + col], anchor="w")
            self.pend_tree.column(col, width=w, anchor="w")
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

        # -- flights tab
        fl = ttk.Frame(nb)
        nb.add(fl, text=self.t["tab_flights"])
        ttk.Label(fl, text=self.t["fl_intro"], wraplength=1080,
                  foreground="#444").pack(anchor="w", padx=8, pady=(8, 6))
        self.fl_men: Dict[int, Dict] = {}
        self.fl_plan: Dict[int, Optional[int]] = {}
        self.fl_cards: Dict[int, tuple] = {}
        self.fl_heads: Dict[int, tk.Label] = {}
        self.fl_alert: set = set()
        self.fl_pick: Optional[int] = None
        board = tk.Frame(fl, background=self.PANEL)
        board.pack(anchor="w", padx=8)
        self._build_board(board)
        tk.Label(fl, text="\u2605 " + self.t["fl_cmd"], background=self.PANEL,
                 foreground=self.ACCENT, font=("", 9), anchor="w").pack(
            anchor="w", padx=10, pady=(8, 0))
        tk.Label(fl, text=self.t["fl_legend"], background=self.PANEL,
                 foreground=self.INK_MUTED, font=("", 9), anchor="w",
                 justify="left", wraplength=1060).pack(anchor="w", padx=10, pady=(2, 0))
        ttk.Separator(fl).pack(fill="x", padx=8, pady=(10, 6))
        tk.Label(fl, text=self.t["fl_bench"], background=self.PANEL,
                 foreground=self.ACCENT_DARK, font=("Georgia", 10, "bold"),
                 anchor="w").pack(anchor="w", padx=10)
        tk.Label(fl, text=self.t["fl_bench_hint"], background=self.PANEL,
                 foreground=self.INK_MUTED, font=("", 9), anchor="w").pack(
            anchor="w", padx=10, pady=(0, 4))
        bcols = ("who", "stats", "ai", "boost", "fat", "state")
        self.bench_tree = ttk.Treeview(fl, columns=bcols, show="headings",
                                       height=5, selectmode="browse")
        self.bench_tree.tag_configure("odd", background=self.STRIPE)
        self.bench_tree.tag_configure("gone", foreground=self.BAD)
        for col, head, width in (
                ("who", self.t["pend_col_who"], 180),
                ("stats", self.t["fl_b_stats"], 90),
                ("ai", self.t["fl_ai"], 60),
                ("boost", self.t["fl_b_boost"], 90),
                ("fat", self.t["fl_fat"], 90),
                ("state", self.t["pend_col_status"], 120)):
            self.bench_tree.heading(col, text=head, anchor="w")
            self.bench_tree.column(col, width=width, anchor="w")
        self.bench_tree.pack(fill="x", padx=10, pady=(0, 4))
        self.bench_tree.bind("<<TreeviewSelect>>", self._pick_bench)
        self.fl_up: Optional[int] = None

        frow = ttk.Frame(fl)
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
        self._fill_flights()

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
            since = corrections.awards_since_apply(self.career.path, data) if data else []
        except sqlite3.Error:
            since = []
        if since:
            ttk.Label(self.aw_frame, text=self.t["awards_since"], wraplength=700).pack(anchor="w")
            self.aw_vars = []
            for a in since:
                v = tk.BooleanVar(value=False)
                ttk.Checkbutton(self.aw_frame, variable=v,
                                text=f"#{a['id']}  pilot {a['pilotId']}  award {a['type']}  {a['earnedDate']}").pack(anchor="w")
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
        # everyone ticked but the dead - those are opted in, not out
        self.pend_checked = {a["id"] for a in self.pending
                             if a["status"] not in ("kia", "mia")}
        for n, a in enumerate(self.pending):
            tags = (("gone",) if a["status"] in ("kia", "mia") else ()) + (("odd",) if n % 2 else ())
            self.pend_tree.insert("", "end", iid=str(a["id"]), tags=tags,
                                  values=(a["who"], self.t["st_" + a["status"]],
                                          a["award"], a["earned"]))
        self._mark_pending()

    def _mark_pending(self) -> None:
        """Redraw the ticks and the running cost."""
        for a in self.pending:
            on = a["id"] in self.pend_checked
            self.pend_tree.item(str(a["id"]), values=(
                ("✓  " if on else "   ") + a["who"],
                self.t["st_" + a["status"]], a["award"], a["earned"]))
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
        self._fill_pending()

    # -- flights ---------------------------------------------------------------

    def _build_board(self, board: tk.Frame) -> None:
        """
        The six flights as the Combat Units screen draws them: a column each,
        four seats down it, a rule between the two sections. The structure
        never changes, so it is built once and only repainted afterwards.
        """
        for f in range(Career.FLIGHTS):
            col = tk.Frame(board, background=self.PANEL)
            col.grid(row=0, column=f, padx=2, sticky="n")
            head = tk.Label(col, text=self.t[f"fl_c{f + 1}"], background=self.DESK,
                            foreground=self.ACCENT_DARK, font=("Georgia", 10, "bold"),
                            width=17, pady=4)
            head.pack(fill="x")
            self.fl_heads[f] = head
            for pos in range(4):
                if pos == 2:                      # the section rule
                    tk.Frame(col, background=self.BORDER, height=1).pack(fill="x", pady=2)
                slot = f * 4 + pos
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
        self.fl_men, self.fl_plan = {}, {s: None for s in range(Career.SEATS)}
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
            if man["hurt"]:
                tags.append("gone")
            self.bench_tree.insert(
                "", "end", iid=str(man["id"]), tags=tuple(tags), values=(
                    man["who"],
                    f"{man['sk'] + 1}/{man['di'] + 1}/{man['co'] + 1}",
                    man["ai"],
                    "/".join(str(b) for b in man["boost"]),
                    f"{man['fatigue']}/{Career.FATIGUE_MAX}",
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
        for flight, head in self.fl_heads.items():
            seats = set(range(flight * 4, flight * 4 + 4))
            title = self.t[f"fl_c{flight + 1}"]
            if seats and seats <= self.fl_alert:
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
            lead = slot % 4 == 0             # a flight lead: he may command
            if man is None:
                who.configure(text=self.t["fl_empty"], foreground="#a3947c")
                line.configure(text="")
                stat.configure(text="")
                note.configure(text="\u2605" if lead else "")
                continue
            hurt, tired = man["hurt"], man["tired"]
            who.configure(text=man["short"],
                          foreground=self.BAD if hurt else self.INK)
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
            if man["fatigue"]:
                bits.append(f"{self.t['fl_fat']} {man['fatigue']}/{Career.FATIGUE_MAX}")
            if hurt:
                bits.append(self.t["fl_hurt"])
            elif tired:
                bits.append(self.t["fl_rest"])
            stat.configure(text=" \u00b7 ".join(bits),
                           foreground=self.BAD if (hurt or tired) else self.INK_MUTED)
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
        self.fl_plan = {s: None for s in range(Career.SEATS)}
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
