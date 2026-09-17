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

import datetime as dt
import locale
import shutil
import sqlite3
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Dict, List, Optional

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
        "title": "IL-2 Korea Career Helper",
        "career": "Career",
        "no_game": "No IL-2 Korea installation found.",
        "no_careers": "No careers found.",
        "tab_revive": "Revive a pilot",
        "tab_points": "Award points",
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
        "locked": "The career file is in use - close IL-2 Korea and try again.",
        "failed": "That did not work: {error}",
        "player_note": "The player's own character is not listed: the game carries the career on with a successor, and this tool leaves that alone.",
        "refresh": "Refresh",
        "tab_times": "Flight time",
        "times_intro": "Missions you flew in less than half the briefed time - warped to the target - re-timed to the plan, as the game does for missions flown without you. Computing only writes the tracker's own record; 'Apply' writes the credited hours into the career for the pilot screen and the hours-based awards, and 'Restore' takes them back.",
        "col_mission": "Mission",
        "col_flown": "Flown",
        "col_planned": "Planned",
        "col_source": "Warps from",
        "col_applied": "In the career",
        "src_log": "flight log",
        "src_plan": "plan only",
        "applied": "applied",
        "not_applied": "-",
        "compute": "Compute",
        "computed": "{n} missions re-timed; the tracker shows them with the switch on.",
        "apply": "Apply credited hours",
        "restore": "Restore game hours",
        "apply_confirm": "Write the credited hours of {n} missions into the career? A backup is made first.",
        "restore_confirm": "Put the game's own hours back for {n} missions?",
        "applied_done": "Credited hours applied to {n} missions. Backup: {backup}",
        "restored_done": "Game hours restored for {n} missions. Backup: {backup}",
        "no_times": "No warped missions found - either you fly the whole route, or nothing has been flown yet.",
        "awards_since": "Awards granted since the hours were applied - tick the ones to withdraw (an award earned on kills should stay):",
        "withdraw": "Withdraw ticked awards",
        "withdrawn": "{n} awards withdrawn. Backup: {backup}",
    },
    "de": {
        "title": "IL-2 Korea Laufbahn-Helfer",
        "career": "Laufbahn",
        "no_game": "Keine IL-2-Korea-Installation gefunden.",
        "no_careers": "Keine Laufbahnen gefunden.",
        "tab_revive": "Piloten zurückholen",
        "tab_points": "Auszeichnungspunkte",
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
        "locked": "Die Laufbahndatei ist in Benutzung - IL-2 Korea schließen und erneut versuchen.",
        "failed": "Das hat nicht geklappt: {error}",
        "player_note": "Der eigene Charakter des Spielers wird nicht aufgeführt: das Spiel führt die Laufbahn mit einem Nachfolger fort, und dieses Werkzeug lässt das unangetastet.",
        "refresh": "Aktualisieren",
        "tab_times": "Flugzeit",
        "times_intro": "Einsätze, die Sie in weniger als der halben geplanten Zeit geflogen sind - zum Ziel gesprungen -, auf den Plan umgerechnet, so wie das Spiel es bei Einsätzen ohne Sie tut. Berechnen schreibt nur die eigene Aufzeichnung der Dienstakte; 'Übernehmen' trägt die angerechneten Stunden in die Laufbahn ein (Pilotenbildschirm, stundenabhängige Auszeichnungen), 'Zurücksetzen' nimmt sie wieder heraus.",
        "col_mission": "Einsatz",
        "col_flown": "Geflogen",
        "col_planned": "Geplant",
        "col_source": "Sprünge aus",
        "col_applied": "In der Laufbahn",
        "src_log": "Fluglog",
        "src_plan": "nur Plan",
        "applied": "übernommen",
        "not_applied": "-",
        "compute": "Berechnen",
        "computed": "{n} Einsätze umgerechnet; die Dienstakte zeigt sie mit eingeschaltetem Schalter.",
        "apply": "Angerechnete Stunden übernehmen",
        "restore": "Spielstunden zurücksetzen",
        "apply_confirm": "Die angerechneten Stunden von {n} Einsätzen in die Laufbahn schreiben? Vorher wird eine Sicherung angelegt.",
        "restore_confirm": "Die Stunden des Spiels für {n} Einsätze wiederherstellen?",
        "applied_done": "Angerechnete Stunden für {n} Einsätze übernommen. Sicherung: {backup}",
        "restored_done": "Spielstunden für {n} Einsätze wiederhergestellt. Sicherung: {backup}",
        "no_times": "Keine Einsätze mit Zeitsprung gefunden - entweder fliegen Sie die ganze Strecke, oder es wurde noch nichts geflogen.",
        "awards_since": "Seit dem Übernehmen der Stunden verliehene Auszeichnungen - die zu entziehenden ankreuzen (eine mit Abschüssen verdiente sollte bleiben):",
        "withdraw": "Angekreuzte Auszeichnungen entziehen",
        "withdrawn": "{n} Auszeichnungen entzogen. Sicherung: {backup}",
    },
    "es": {
        "title": "Asistente de carrera IL-2 Korea",
        "career": "Carrera",
        "no_game": "No se encontró ninguna instalación de IL-2 Korea.",
        "no_careers": "No se encontraron carreras.",
        "tab_revive": "Recuperar a un piloto",
        "tab_points": "Puntos de condecoración",
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
        "locked": "El archivo de la carrera está en uso: cierre IL-2 Korea e inténtelo de nuevo.",
        "failed": "No ha funcionado: {error}",
        "player_note": "El personaje del jugador no aparece: el juego continúa la carrera con un sucesor y esta herramienta no lo toca.",
        "refresh": "Actualizar",
        "tab_times": "Tiempo de vuelo",
        "times_intro": "Misiones voladas en menos de la mitad del tiempo previsto - saltando al objetivo -, ajustadas al plan como hace el juego con las misiones voladas sin usted. Calcular solo escribe el registro propio de la Hoja de Servicios; 'Aplicar' escribe las horas acreditadas en la carrera (pantalla del piloto, condecoraciones por horas) y 'Restaurar' las retira.",
        "col_mission": "Misión",
        "col_flown": "Volado",
        "col_planned": "Previsto",
        "col_source": "Saltos desde",
        "col_applied": "En la carrera",
        "src_log": "registro de vuelo",
        "src_plan": "solo plan",
        "applied": "aplicado",
        "not_applied": "-",
        "compute": "Calcular",
        "computed": "{n} misiones ajustadas; la Hoja de Servicios las muestra con el interruptor activado.",
        "apply": "Aplicar horas acreditadas",
        "restore": "Restaurar horas del juego",
        "apply_confirm": "¿Escribir las horas acreditadas de {n} misiones en la carrera? Antes se hace una copia de seguridad.",
        "restore_confirm": "¿Restaurar las horas propias del juego en {n} misiones?",
        "applied_done": "Horas acreditadas aplicadas a {n} misiones. Copia de seguridad: {backup}",
        "restored_done": "Horas del juego restauradas en {n} misiones. Copia de seguridad: {backup}",
        "no_times": "No se encontraron misiones con salto: o vuela toda la ruta, o aún no se ha volado nada.",
        "awards_since": "Condecoraciones concedidas desde que se aplicaron las horas - marque las que quiera retirar (una ganada por derribos debería quedarse):",
        "withdraw": "Retirar las marcadas",
        "withdrawn": "{n} condecoraciones retiradas. Copia de seguridad: {backup}",
    },
    "fr": {
        "title": "Assistant de carrière IL-2 Korea",
        "career": "Carrière",
        "no_game": "Aucune installation d’IL-2 Korea trouvée.",
        "no_careers": "Aucune carrière trouvée.",
        "tab_revive": "Ramener un pilote",
        "tab_points": "Points de décoration",
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
        "locked": "Le fichier de carrière est en cours d’utilisation : fermez IL-2 Korea et réessayez.",
        "failed": "Cela n’a pas fonctionné : {error}",
        "player_note": "Le personnage du joueur n’est pas listé : le jeu poursuit la carrière avec un successeur, et cet outil n’y touche pas.",
        "refresh": "Actualiser",
        "tab_times": "Temps de vol",
        "times_intro": "Missions volées en moins de la moitié du temps prévu - saut vers l’objectif -, recalées sur le plan comme le jeu le fait pour les missions volées sans vous. Calculer n’écrit que le registre propre de l’état de service ; « Appliquer » inscrit les heures créditées dans la carrière (écran du pilote, décorations aux heures) et « Rétablir » les retire.",
        "col_mission": "Mission",
        "col_flown": "Volé",
        "col_planned": "Prévu",
        "col_source": "Sauts d’après",
        "col_applied": "Dans la carrière",
        "src_log": "journal de vol",
        "src_plan": "plan seul",
        "applied": "appliqué",
        "not_applied": "-",
        "compute": "Calculer",
        "computed": "{n} missions recalées ; l’état de service les affiche avec l’interrupteur activé.",
        "apply": "Appliquer les heures créditées",
        "restore": "Rétablir les heures du jeu",
        "apply_confirm": "Inscrire les heures créditées de {n} missions dans la carrière ? Une sauvegarde est faite d’abord.",
        "restore_confirm": "Remettre les heures propres du jeu pour {n} missions ?",
        "applied_done": "Heures créditées appliquées à {n} missions. Sauvegarde : {backup}",
        "restored_done": "Heures du jeu rétablies pour {n} missions. Sauvegarde : {backup}",
        "no_times": "Aucune mission avec saut trouvée : soit vous volez toute la route, soit rien n’a encore été volé.",
        "awards_since": "Décorations attribuées depuis l’application des heures - cochez celles à retirer (une décoration gagnée par des victoires doit rester) :",
        "withdraw": "Retirer les décorations cochées",
        "withdrawn": "{n} décorations retirées. Sauvegarde : {backup}",
    },
    "ru": {
        "title": "Помощник карьеры IL-2 Korea",
        "career": "Карьера",
        "no_game": "Установка IL-2 Korea не найдена.",
        "no_careers": "Карьеры не найдены.",
        "tab_revive": "Вернуть лётчика",
        "tab_points": "Наградные очки",
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
        "locked": "Файл карьеры занят — закройте IL-2 Korea и попробуйте снова.",
        "failed": "Не получилось: {error}",
        "player_note": "Персонаж игрока не показан: игра продолжает карьеру преемником, и этот инструмент этого не трогает.",
        "refresh": "Обновить",
        "tab_times": "Лётное время",
        "times_intro": "Вылеты, пройденные менее чем за половину планового времени — с перемоткой к цели, — пересчитанные по плану, как игра делает для вылетов без вас. «Рассчитать» пишет только собственную запись послужного списка; «Применить» вносит зачтённые часы в карьеру (экран лётчика, награды за часы), «Вернуть» убирает их.",
        "col_mission": "Вылет",
        "col_flown": "Налёт",
        "col_planned": "По плану",
        "col_source": "Перемотки из",
        "col_applied": "В карьере",
        "src_log": "журнала полёта",
        "src_plan": "только плана",
        "applied": "применено",
        "not_applied": "-",
        "compute": "Рассчитать",
        "computed": "Пересчитано вылетов: {n}; послужной список показывает их при включённом переключателе.",
        "apply": "Применить зачтённые часы",
        "restore": "Вернуть часы игры",
        "apply_confirm": "Записать зачтённые часы {n} вылетов в карьеру? Сначала будет сделана резервная копия.",
        "restore_confirm": "Вернуть собственные часы игры для {n} вылетов?",
        "applied_done": "Зачтённые часы применены к {n} вылетам. Резервная копия: {backup}",
        "restored_done": "Часы игры возвращены для {n} вылетов. Резервная копия: {backup}",
        "no_times": "Вылетов с перемоткой не найдено — либо вы летаете весь маршрут, либо ещё ничего не налётано.",
        "awards_since": "Награды, вручённые после применения часов — отметьте те, что нужно отозвать (заслуженная сбитыми должна остаться):",
        "withdraw": "Отозвать отмеченные",
        "withdrawn": "Отозвано наград: {n}. Резервная копия: {backup}",
    },
    "zh": {
        "title": "IL-2 Korea 生涯助手",
        "career": "生涯",
        "no_game": "未找到 IL-2 Korea 安装。",
        "no_careers": "未找到生涯。",
        "tab_revive": "复活飞行员",
        "tab_points": "授勋点数",
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
        "locked": "生涯文件正在使用中——请关闭 IL-2 Korea 后重试。",
        "failed": "操作失败：{error}",
        "player_note": "玩家自己的角色不在列表中：游戏会以继任者延续生涯，本工具不作改动。",
        "refresh": "刷新",
        "tab_times": "飞行时间",
        "times_intro": "以少于简报时间一半飞完的任务——即跳跃至目标的任务——按计划重新计时，如同游戏对无您参与的任务所做。“计算”只写入服役记录自己的记录；“应用”把计入的小时数写入生涯（飞行员界面、按小时授予的奖励），“恢复”则将其撤回。",
        "col_mission": "任务",
        "col_flown": "实飞",
        "col_planned": "计划",
        "col_source": "跳跃来源",
        "col_applied": "已写入生涯",
        "src_log": "飞行日志",
        "src_plan": "仅计划",
        "applied": "已应用",
        "not_applied": "-",
        "compute": "计算",
        "computed": "已重新计时 {n} 个任务；打开开关后服役记录将显示。",
        "apply": "应用计入的小时数",
        "restore": "恢复游戏小时数",
        "apply_confirm": "将 {n} 个任务的计入小时数写入生涯？会先创建备份。",
        "restore_confirm": "恢复 {n} 个任务的游戏原始小时数？",
        "applied_done": "已将计入小时数应用于 {n} 个任务。备份：{backup}",
        "restored_done": "已恢复 {n} 个任务的游戏小时数。备份：{backup}",
        "no_times": "未找到跳跃任务——您要么飞完了全程，要么尚未出击。",
        "awards_since": "应用小时数后授予的奖励——勾选要撤销的（凭击落获得的应保留）：",
        "withdraw": "撤销勾选的奖励",
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

    # -- flight-time corrections -------------------------------------------

    def corrections(self):
        return corrections.load(self.name)

    def compute_corrections(self, game: Path):
        data = corrections.compute(self.path, game, existing=corrections.load(self.name))
        corrections.save(self.name, data)
        return data

    def apply_hours(self, keys) -> Path:
        backup = self.backup()
        data = corrections.load(self.name) or {"missions": {}}
        done = corrections.apply_hours(self.path, data, keys)
        corrections.save(self.name, data)
        return backup, done

    def restore_hours(self, keys):
        backup = self.backup()
        data = corrections.load(self.name) or {"missions": {}}
        done = corrections.restore_hours(self.path, data, keys)
        corrections.save(self.name, data)
        return backup, done

    def award_points(self) -> int:
        with self._open() as con:
            return int(con.execute("SELECT awardPoints FROM squadron").fetchone()[0] or 0)

    # -- writes ------------------------------------------------------------

    def backup(self) -> Path:
        BACKUPS.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        # Not ".db": the game lists every .db in its Career folder, and this
        # folder is elsewhere anyway, but the extension is changed as well so
        # a copy can never be mistaken for a live career. A counter keeps two
        # writes in the same second from sharing one backup.
        n = 0
        while True:
            target = BACKUPS / f"{self.name}.{stamp}{'' if n == 0 else f'-{n}'}.career-backup"
            if not target.exists():
                break
            n += 1
        shutil.copy2(self.path, target)
        return target

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

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.t = STRINGS[pick_language()]
        self.title(self.t["title"])
        self.geometry("760x460")
        self.minsize(640, 400)
        self.careers: List[Career] = []
        self.career: Optional[Career] = None
        self.lost: List[Dict] = []
        self._build()
        self._load_careers()

    # -- layout --------------------------------------------------------------

    def _build(self) -> None:
        pad = {"padx": 10, "pady": 6}
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
        for key, width in (("name", 260), ("state", 160), ("date", 110), ("can", 200)):
            self.tree.heading(key, text=self.t["col_" + key])
            self.tree.column(key, width=width, anchor="w")
        self.tree.pack(fill="both", expand=True, padx=8)
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._update_buttons())
        bottom = ttk.Frame(rev)
        bottom.pack(fill="x", padx=8, pady=8)
        self.plane_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(bottom, text=self.t["restore_plane"], variable=self.plane_var).pack(side="left")
        self.revive_btn = ttk.Button(bottom, text=self.t["revive"], command=self._revive, state="disabled")
        self.revive_btn.pack(side="right")

        # -- flight time tab
        ft = ttk.Frame(nb)
        nb.add(ft, text=self.t["tab_times"])
        ttk.Label(ft, text=self.t["times_intro"], wraplength=700).pack(anchor="w", padx=8, pady=(8, 6))
        cols = ("mission", "flown", "planned", "source", "applied")
        self.ft_tree = ttk.Treeview(ft, columns=cols, show="headings", height=7, selectmode="extended")
        for key, width in (("mission", 200), ("flown", 90), ("planned", 90), ("source", 130), ("applied", 130)):
            self.ft_tree.heading(key, text=self.t["col_" + key])
            self.ft_tree.column(key, width=width, anchor="w")
        self.ft_tree.pack(fill="both", expand=True, padx=8)
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

        self.status = tk.StringVar()
        ttk.Label(self, textvariable=self.status, wraplength=740, foreground="#444").pack(
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
            points = self.career.award_points()
        except sqlite3.Error as exc:
            self.status.set(self.t["failed"].format(error=exc))
            return
        self.rule_var.set(self.t["rule"].format(date=today))
        self.tree.delete(*self.tree.get_children())
        for p in self.lost:
            self.tree.insert("", "end", iid=str(p["id"]), values=(
                p["name"], self.t[STATE_NAMES[p["state"]]], p["lost_on"],
                self.t["yes"] if p["revivable"] else self.t["no"]))
        if not self.lost:
            self.status.set(self.t["no_dead"])
        else:
            self.status.set("")
        self.points_var.set(self.t["points_now"].format(points=points))
        self._update_buttons()
        self._fill_times()

    def _selected(self) -> Optional[Dict]:
        sel = self.tree.selection()
        if not sel:
            return None
        return next((p for p in self.lost if str(p["id"]) == sel[0]), None)

    def _update_buttons(self) -> None:
        p = self._selected()
        self.revive_btn["state"] = "normal" if (p and p["revivable"]) else "disabled"

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
        for key in sorted(entries, key=int):
            e = entries[key]
            self.ft_tree.insert("", "end", iid=key, values=(
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

    def _ft_selected(self, want_applied: bool):
        data = self.career.corrections() if self.career else None
        entries = (data or {}).get("missions", {})
        keys = list(self.ft_tree.selection()) or list(entries)
        return [k for k in keys if bool(entries.get(k, {}).get("applied")) == want_applied]

    def _apply_hours(self) -> None:
        keys = self._ft_selected(want_applied=False)
        if not keys or not messagebox.askyesno(self.t["title"], self.t["apply_confirm"].format(n=len(keys))):
            return
        try:
            backup, done = self.career.apply_hours(keys)
        except sqlite3.OperationalError:
            messagebox.showerror(self.t["title"], self.t["locked"])
            return
        except Exception as exc:          # noqa: BLE001
            messagebox.showerror(self.t["title"], self.t["failed"].format(error=exc))
            return
        self.status.set(self.t["applied_done"].format(n=len(done), backup=backup))
        self._fill_times()

    def _restore_hours(self) -> None:
        keys = self._ft_selected(want_applied=True)
        if not keys or not messagebox.askyesno(self.t["title"], self.t["restore_confirm"].format(n=len(keys))):
            return
        try:
            backup, done = self.career.restore_hours(keys)
        except sqlite3.OperationalError:
            messagebox.showerror(self.t["title"], self.t["locked"])
            return
        except Exception as exc:          # noqa: BLE001
            messagebox.showerror(self.t["title"], self.t["failed"].format(error=exc))
            return
        self.status.set(self.t["restored_done"].format(n=len(done), backup=backup))
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


def main() -> int:
    app = App()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
