; IL-2 Korea Service Record + Awards Mod
;
; One installer, two payloads:
;   * the tracker, a self-contained application, into {localappdata}
;   * the awards mod, a set of loose files, into the user's game folder
;
; The two are unrelated at runtime. The tracker reads whatever the game holds,
; so it works with or without the mod; the mod works with or without the
; tracker. They ship together because the same person made both and the folder
; the mod needs is the folder this installer already asks for.
;
; How IL-2 modding actually works, which shapes the whole install and uninstall:
; with modifications enabled, the game looks for a file under data\ first and
; only falls back to the .gtp archive when there is none. With modifications
; disabled it goes straight to the archive and ignores data\ entirely. So every
; file this mod ships is an *addition* to a folder tree that is otherwise empty
; of it — nothing is replaced, there is nothing to back up, and uninstalling is
; simply deleting what was added. The game then finds nothing loose and reads
; the archive again, exactly as it did before.
;
; Build:  pyinstaller korea_service_record.spec --noconfirm
;         python tools/stage_release.py
;         iscc installer\IL2_Korea_Service_Record.iss

#define MyAppName "IL-2 Korea Service Record"
#define MyAppExeName "IL2_Korea_Service_Record.exe"
#define MyAppVersion "1.6.1"
#define MyAppPublisher "Arrow_1"

[Setup]
; Keep this GUID stable for the life of the product — it is how Windows knows
; an install is an upgrade rather than a second copy.
AppId={{7C4E1B92-3A6D-4F58-9E21-5D0C8A47B3F1}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
; Per-user by default, which is what {localappdata} means. Running elevated
; would resolve {localappdata} to the *administrator's* profile and install the
; tracker where the player cannot see it. The override lets Windows offer
; elevation for the one case that needs it: a game folder under Program Files.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={localappdata}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
OutputBaseFilename=IL2_Korea_Service_Record_Setup_v{#MyAppVersion}
OutputDir=Output
Compression=lzma
SolidCompression=yes
UninstallDisplayName={#MyAppName}
; The exe carries the icon internally, so the Start Menu entry, the taskbar
; and Add/Remove Programs all pick it up from there. Only the setup program
; itself needs telling.
UninstallDisplayIcon={app}\{#MyAppExeName}
SetupIconFile=IL2_Korea_Service_Record.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
; Not part of the Inno Setup distribution (it is one of the "unofficial"
; translations), so the CI runner's install lacks it: shipped in the repo.
Name: "chinesesimplified"; MessagesFile: "Languages\ChineseSimplified.isl"

[CustomMessages]
english.IL2PageTitle=Select your IL-2 Korea installation
english.IL2PageDescription=The tracker reads your careers from here. The awards mod, if you install it, is copied into this folder.
english.IL2PagePrompt=Choose the folder IL-2 Sturmovik: Korea is installed in.
english.InvalidIL2Folder=That folder does not look like an IL-2 Korea installation.%n%nChoose the folder the game is installed in — the one holding a data folder, or the folder just above it if your copy keeps everything in a game subfolder.%n%nFor example:%n    F:\IL2Series%n    F:\IL2Series\game%n    ...\steamapps\common\IL2Series
english.ComponentTracker=Service Record (the tracker application)
english.ComponentMod=Awards mod (adds decorations to the career)
english.ComponentModExtended=Extended promotions: earned on merit, with two flag ranks for every nation (recommended)
english.ComponentModStock=Stock promotions, corrected: the original criteria, with the missing promotion out of Major restored
english.ModsDisabled=Modifications are currently switched off in IL-2 Korea.%n%nThe awards mod will be installed, but the game will ignore it until you turn modifications on:%n%n    Settings  ->  General  ->  Enable modifications%n%nInstall it anyway?
english.RemovePhotosTitle=Also remove your pilot photographs and settings?%n%nLocation: %%LOCALAPPDATA%%\IL2KoreaTracker%n%nYES deletes them.%nNO keeps them for a future install.%n%nFlight-time corrections and career backups are always kept: they record changes made to the game's own career files.
english.CreateDesktopIcon=Create a &desktop icon
english.Installed=Setup has installed %3 into%n%1%n%nStart it from the Start Menu; it opens in your browser, with a small star by the clock. Settings, photographs, flight-time corrections and career backups live in%n%2

german.IL2PageTitle=IL-2 Korea Installation auswählen
german.IL2PageDescription=Der Tracker liest Ihre Karrieren von hier. Der Auszeichnungs-Mod wird, falls gewählt, in diesen Ordner kopiert.
german.IL2PagePrompt=Wählen Sie den Ordner, in dem IL-2 Sturmovik: Korea installiert ist.
german.InvalidIL2Folder=Dieser Ordner scheint keine IL-2 Korea Installation zu sein.%n%nWählen Sie den Ordner, in dem das Spiel installiert ist — jenen mit dem Unterordner data, oder den Ordner direkt darüber, falls Ihre Version alles in einem Unterordner game ablegt.%n%nZum Beispiel:%n    F:\IL2Series%n    F:\IL2Series\game%n    ...\steamapps\common\IL2Series
german.ComponentTracker=Dienstakte (die Tracker-Anwendung)
german.ComponentMod=Auszeichnungs-Mod (ergänzt Orden in der Karriere)
german.ComponentModExtended=Erweiterte Beförderungen: nach Verdienst, mit zwei Generalsrängen für jede Nation (empfohlen)
german.ComponentModStock=Originale Beförderungen, korrigiert: die ursprünglichen Kriterien, mit der fehlenden Beförderung vom Major wiederhergestellt
german.ModsDisabled=Modifikationen sind in IL-2 Korea derzeit ausgeschaltet.%n%nDer Auszeichnungs-Mod wird installiert, das Spiel ignoriert ihn jedoch, bis Sie Modifikationen einschalten:%n%n    Einstellungen  ->  Allgemein  ->  Modifikationen aktivieren%n%nTrotzdem installieren?
german.RemovePhotosTitle=Auch Ihre Pilotenfotos und Einstellungen entfernen?%n%nSpeicherort: %%LOCALAPPDATA%%\IL2KoreaTracker%n%nJA löscht sie.%nNEIN behält sie für eine spätere Installation.%n%nFlugzeit-Korrekturen und Laufbahn-Sicherungen bleiben immer erhalten: sie dokumentieren Änderungen an den Laufbahndateien des Spiels.
german.CreateDesktopIcon=&Desktop-Symbol erstellen
german.Installed=Setup hat %3 installiert nach%n%1%n%nStarten Sie es über das Startmenü; es öffnet sich im Browser, mit einem kleinen Stern neben der Uhr. Einstellungen, Fotos, Flugzeit-Korrekturen und Laufbahn-Sicherungen liegen in%n%2

french.IL2PageTitle=Sélectionnez votre installation d'IL-2 Corée
french.IL2PageDescription=Le carnet lit vos carrières ici. Le mod de décorations, si vous l'installez, est copié dans ce dossier.
french.IL2PagePrompt=Choisissez le dossier où IL-2 Sturmovik: Korea est installé.
french.InvalidIL2Folder=Ce dossier ne semble pas être une installation d'IL-2 Corée.%n%nChoisissez le dossier où le jeu est installé — celui qui contient un dossier data, ou le dossier juste au-dessus si votre version place tout dans un sous-dossier game.%n%nPar exemple :%n    F:\IL2Series%n    F:\IL2Series\game%n    ...\steamapps\common\IL2Series
french.ComponentTracker=État de service (l'application)
french.ComponentMod=Mod de décorations (ajoute des décorations à la carrière)
french.ComponentModExtended=Promotions étendues : au mérite, avec deux grades d'officier général pour chaque nation (recommandé)
french.ComponentModStock=Promotions d'origine, corrigées : les critères initiaux, avec la promotion manquante depuis Commandant rétablie
french.ModsDisabled=Les modifications sont actuellement désactivées dans IL-2 Corée.%n%nLe mod sera installé, mais le jeu l'ignorera tant que vous n'aurez pas activé les modifications :%n%n    Paramètres  ->  Général  ->  Activer les modifications%n%nInstaller quand même ?
french.RemovePhotosTitle=Supprimer aussi vos photographies de pilote et vos réglages ?%n%nEmplacement : %%LOCALAPPDATA%%\IL2KoreaTracker%n%nOUI les supprime.%nNON les conserve.%n%nLes corrections de temps de vol et les sauvegardes de carrière sont toujours conservées : elles consignent des modifications faites aux fichiers de carrière du jeu.
french.CreateDesktopIcon=Créer une icône sur le &Bureau
french.Installed=L’installation a placé %3 dans%n%1%n%nLancez-le depuis le menu Démarrer ; il s’ouvre dans votre navigateur, avec une petite étoile près de l’horloge. Réglages, photographies, corrections de temps de vol et sauvegardes de carrière sont dans%n%2

spanish.IL2PageTitle=Seleccione su instalación de IL-2 Corea
spanish.IL2PageDescription=La hoja de servicios lee sus carreras de aquí. El mod de condecoraciones, si lo instala, se copia en esta carpeta.
spanish.IL2PagePrompt=Elija la carpeta donde está instalado IL-2 Sturmovik: Korea.
spanish.InvalidIL2Folder=Esa carpeta no parece una instalación de IL-2 Corea.%n%nElija la carpeta donde está instalado el juego — la que contiene una carpeta data, o la carpeta inmediatamente superior si su copia lo guarda todo en una subcarpeta game.%n%nPor ejemplo:%n    F:\IL2Series%n    F:\IL2Series\game%n    ...\steamapps\common\IL2Series
spanish.ComponentTracker=Hoja de servicios (la aplicación)
spanish.ComponentMod=Mod de condecoraciones (añade condecoraciones a la carrera)
spanish.ComponentModExtended=Ascensos ampliados: por méritos, con dos rangos de oficial general para cada nación (recomendado)
spanish.ComponentModStock=Ascensos originales, corregidos: los criterios iniciales, con el ascenso desde Mayor que faltaba restaurado
spanish.ModsDisabled=Las modificaciones están desactivadas en IL-2 Corea.%n%nEl mod se instalará, pero el juego lo ignorará hasta que active las modificaciones:%n%n    Ajustes  ->  General  ->  Activar modificaciones%n%n¿Instalar de todos modos?
spanish.RemovePhotosTitle=¿Eliminar también sus fotografías de piloto y ajustes?%n%nUbicación: %%LOCALAPPDATA%%\IL2KoreaTracker%n%nSÍ los elimina.%nNO los conserva.%n%nLas correcciones de tiempo de vuelo y las copias de seguridad de carrera se conservan siempre: registran cambios hechos en los archivos de carrera del propio juego.
spanish.CreateDesktopIcon=Crear un icono en el &escritorio
spanish.Installed=Se ha instalado %3 en%n%1%n%nInícielo desde el menú Inicio; se abre en su navegador, con una pequeña estrella junto al reloj. Ajustes, fotografías, correcciones de tiempo de vuelo y copias de seguridad de carrera están en%n%2

russian.IL2PageTitle=Выберите установку IL-2 Корея
russian.IL2PageDescription=Послужной список читает ваши карьеры отсюда. Мод наград, если вы его установите, копируется в эту папку.
russian.IL2PagePrompt=Укажите папку, в которую установлена IL-2 Sturmovik: Korea.
russian.InvalidIL2Folder=Эта папка не похожа на установку IL-2 Корея.%n%nВыберите папку, в которую установлена игра — ту, где есть папка data, или папку уровнем выше, если в вашей версии всё лежит во вложенной папке game.%n%nНапример:%n    F:\IL2Series%n    F:\IL2Series\game%n    ...\steamapps\common\IL2Series
russian.ComponentTracker=Послужной список (приложение)
russian.ComponentMod=Мод наград (добавляет награды в карьеру)
russian.ComponentModExtended=Расширенные повышения: по заслугам, с двумя генеральскими званиями для каждой страны (рекомендуется)
russian.ComponentModStock=Исходные повышения, исправленные: прежние критерии, с восстановленным повышением из майоров
russian.ModsDisabled=Модификации в IL-2 Корея сейчас отключены.%n%nМод будет установлен, но игра не увидит его, пока вы не включите модификации:%n%n    Настройки  ->  Общие  ->  Включить модификации%n%nВсё равно установить?
russian.RemovePhotosTitle=Удалить также фотографии лётчиков и настройки?%n%nРасположение: %%LOCALAPPDATA%%\IL2KoreaTracker%n%nДА удалит их.%nНЕТ сохранит.%n%nИсправления лётного времени и резервные копии карьер сохраняются всегда: они фиксируют изменения, внесённые в файлы карьер самой игры.
russian.CreateDesktopIcon=Создать значок на &рабочем столе
russian.Installed=%3 установлен в%n%1%n%nЗапускайте из меню «Пуск»; он открывается в браузере, с маленькой звездой рядом с часами. Настройки, фотографии, исправления лётного времени и резервные копии карьер хранятся в%n%2

chinesesimplified.IL2PageTitle=选择您的 IL-2 朝鲜 安装位置
chinesesimplified.IL2PageDescription=服役档案从此处读取您的生涯。若选择安装勋章模组，也将复制到此文件夹。
chinesesimplified.IL2PagePrompt=请选择 IL-2 Sturmovik: Korea 的安装文件夹。
chinesesimplified.InvalidIL2Folder=该文件夹似乎不是 IL-2 朝鲜 的安装位置。%n%n请选择游戏的安装文件夹 — 即包含 data 子文件夹的那一个；若您的版本将全部内容放在 game 子文件夹中，请选择其上一级文件夹。%n%n例如：%n    F:\IL2Series%n    F:\IL2Series\game%n    ...\steamapps\common\IL2Series
chinesesimplified.ComponentTracker=服役档案（主程序）
chinesesimplified.ComponentMod=勋章模组（为生涯增加勋章）
chinesesimplified.ComponentModExtended=扩展晋升：按功绩晋升，每个国家增加两个将官军衔（推荐）
chinesesimplified.ComponentModStock=原版晋升（已修正）：保留原有条件，并恢复缺失的少校晋升
chinesesimplified.ModsDisabled=IL-2 朝鲜 当前已关闭模组功能。%n%n模组仍会安装，但在您启用模组之前游戏不会读取它：%n%n    设置  ->  常规  ->  启用模组%n%n仍要安装吗？
chinesesimplified.RemovePhotosTitle=同时删除您的飞行员照片与设置？%n%n位置：%%LOCALAPPDATA%%\IL2KoreaTracker%n%n是：删除。%n否：保留以备将来安装。%n%n飞行时间修正和生涯备份始终保留：它们记录了对游戏本身生涯文件所做的更改。
chinesesimplified.CreateDesktopIcon=创建桌面图标(&D)
chinesesimplified.Installed=%3 已安装到%n%1%n%n请从开始菜单启动；它会在浏览器中打开，时钟旁有一颗小星。设置、照片、飞行时间修正和生涯备份保存在%n%2

[Types]
Name: "full"; Description: "{cm:ComponentTracker} + {cm:ComponentMod}"
Name: "trackeronly"; Description: "{cm:ComponentTracker}"
Name: "custom"; Description: "Custom"; Flags: iscustom

[Components]
Name: "tracker"; Description: "{cm:ComponentTracker}"; Types: full trackeronly custom; Flags: fixed
Name: "mod"; Description: "{cm:ComponentMod}"; Types: full
; Two promotion systems, one awards.cfg each. `exclusive` renders the pair as
; radio buttons under the mod, so exactly one is chosen. Both files carry the
; same medal fixes; only the promotion block differs, and the stock variant is
; generated from the extended one by tools/stage_release.py so they cannot
; drift. Inno remembers the choice and pre-selects it on a reinstall.
Name: "mod\extended"; Description: "{cm:ComponentModExtended}"; Types: full; Flags: exclusive
Name: "mod\stock"; Description: "{cm:ComponentModStock}"; Flags: exclusive

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; --- The tracker. Self-contained; ships no game data of any kind. ---
Source: "payload\tracker\*"; DestDir: "{app}"; Components: tracker; \
    Flags: ignoreversion recursesubdirs createallsubdirs

; --- The awards mod, into the folder chosen on the custom page. ---
; The files live flat in mod\assets — that folder is the mod, committed and
; reviewable — and are placed here, which is the only place their destination
; is written down in an executable form. mod\README.txt says the same for
; anyone installing by hand.
;
; Additions to data\, which the game reads in preference to the archives while
; modifications are enabled. Inno records each one and removes it on uninstall,
; which is the whole of the cleanup: with the files gone the game finds nothing
; loose and reads the archives again.
; One of two promotion systems lands as awards.cfg, by the sub-component chosen.
Source: "mod\assets\awards.cfg"; DestDir: "{code:GetIL2Dir}\data\scg\2"; \
    Components: mod\extended; Flags: ignoreversion uninsremovereadonly
Source: "mod\assets\awards.stock.cfg"; DestDir: "{code:GetIL2Dir}\data\scg\2"; DestName: "awards.cfg"; \
    Components: mod\stock; Flags: ignoreversion uninsremovereadonly

Source: "mod\assets\awards.xaml"; DestDir: "{code:GetIL2Dir}\data\nsdata\assets\images"; \
    Components: mod; Flags: ignoreversion uninsremovereadonly
Source: "mod\assets\awards6xx.dds"; DestDir: "{code:GetIL2Dir}\data\nsdata\assets\images"; \
    Components: mod; Flags: ignoreversion uninsremovereadonly
Source: "mod\assets\awards6xx2.dds"; DestDir: "{code:GetIL2Dir}\data\nsdata\assets\images"; \
    Components: mod; Flags: ignoreversion uninsremovereadonly
; The mod's own atlas (1.4.0): everything added after the first three unit
; citations - Silver Star rungs, DSM, NDSM, Commendation ladder, Bronze Star V.
Source: "mod\assets\awards6xx3.dds"; DestDir: "{code:GetIL2Dir}\data\nsdata\assets\images"; \
    Components: mod; Flags: ignoreversion uninsremovereadonly

; The six locale dictionaries carrying the new decorations' names.
Source: "mod\assets\awards.locale=*.json"; \
    DestDir: "{code:GetIL2Dir}\data\nsdata\assets\locale"; \
    Components: mod; Flags: ignoreversion uninsremovereadonly

; The description texts for the added decorations, six languages each.
Source: "mod\assets\6*.locale=*.txt"; \
    DestDir: "{code:GetIL2Dir}\data\nsdata\assets\awards\6xx"; \
    Components: mod; Flags: ignoreversion uninsremovereadonly

; Flag rank — two ranks beyond the six the game ships, for the USSR, PRC, DPRK
; and USAF ladders. Each atlas carries its two new boards in the one free row
; it had left, and ranks.xaml crops them out; the locale files name them,
; without which the game draws its own RANK6016!LOCALIZE! marker.
Source: "mod\assets\Ranks*.dds"; DestDir: "{code:GetIL2Dir}\data\nsdata\assets\images"; \
    Components: mod; Flags: ignoreversion uninsremovereadonly
Source: "mod\assets\ranks.xaml"; DestDir: "{code:GetIL2Dir}\data\nsdata\assets\images"; \
    Components: mod; Flags: ignoreversion uninsremovereadonly
Source: "mod\assets\ranks.locale=*.json"; \
    DestDir: "{code:GetIL2Dir}\data\nsdata\assets\locale"; \
    Components: mod; Flags: ignoreversion uninsremovereadonly

; Manual-install instructions, kept beside the tracker.
Source: "mod\README.txt"; DestDir: "{app}"; DestName: "Awards mod - manual install.txt"; \
    Components: mod; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"

[Registry]
; Remembered so a reinstall prefills the same folder.
Root: HKA; Subkey: "Software\{#MyAppName}"; ValueType: string; \
    ValueName: "IL2Path"; ValueData: "{code:GetIL2Dir}"; Flags: uninsdeletekey

[UninstallDelete]
; Written after installation by [Code], so Inno does not know to remove them.
Type: files; Name: "{app}\locale_setting.txt"
Type: files; Name: "{app}\game_dir.txt"
; Inno removes the files it installed; these are the folders it created for
; them, which would otherwise be left behind empty. Only ever the mod's own
; folder — never data\nsdata\assets, which the game itself uses.
Type: dirifempty; Name: "{code:GetIL2Dir}\data\nsdata\assets\awards\6xx"
Type: dirifempty; Name: "{code:GetIL2Dir}\data\nsdata\assets\awards"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Open the Service Record"; \
    Flags: nowait postinstall skipifsilent

[Code]
var
  IL2Page: TInputDirWizardPage;

function LooksLikeIL2Root(const Dir: string): Boolean;
var
  Found: TFindRec;
begin
  { The .gtp archives are the game's own content and are present in every
    installation, Steam or not, played or not.

    data\Career was the original test and was wrong: the game creates it when
    the first career is started, so a correct game folder was rejected as "not
    IL-2 Korea" by anyone who had installed the game and not yet flown a
    career. Reported on the forum by hawax270, who could not get past this
    page at all. It stays as an alternative below only because it costs
    nothing and covers any layout where the archives have been moved. }
  Result := False;
  if Dir = '' then
    Exit;
  if FindFirst(AddBackslash(Dir) + 'data\*.gtp', Found) then
  begin
    FindClose(Found);
    Result := True;
    Exit;
  end;
  Result := DirExists(AddBackslash(Dir) + 'data\Career');
end;

function FindIL2Root(const Dir: string): string;
var
  Candidate, Parent: string;
  Guard: Integer;
begin
  { Accept the root, its data folder, or anything below — data\Career is the
    folder users know by name, so it is what they browse to.

    Stop when the parent stops changing, which is what a drive root does:
    ExtractFileDir('C:\') is 'C:\'. Comparing against the previous value is
    the only reliable test — 'C:\' is three characters, so a length check
    walks straight past it and the loop never ends. Guard is belt and braces
    against any other path shape that will not shorten. }
  Result := '';
  Candidate := Trim(Dir);
  for Guard := 1 to 32 do
  begin
    if Candidate = '' then
      Exit;
    if LooksLikeIL2Root(Candidate) then
    begin
      Result := Candidate;
      Exit;
    end;
    { The copy sold direct by the developer keeps everything one level deeper:
      F:\IL2Series\game\data, where Steam has ...\IL2Series\data. F:\IL2Series
      is the honest answer to "where is the game installed" and has no data
      folder in it, which is exactly the wall hawax270 hit. }
    if LooksLikeIL2Root(AddBackslash(Candidate) + 'game') then
    begin
      Result := AddBackslash(Candidate) + 'game';
      Exit;
    end;
    Parent := ExtractFileDir(RemoveBackslashUnlessRoot(Candidate));
    if (Parent = '') or (CompareText(Parent, Candidate) = 0) then
      Exit;
    Candidate := Parent;
  end;
end;

function ModificationsEnabled(const Root: string): Boolean;
var
  Settings: string;
  Contents: AnsiString;
  Marker: Integer;
  Tail: string;
begin
  { data\nsdata\UserData\UserSettings.json holds game.enableModifications. With
    it off the game never looks in data\ at all, so the mod installs correctly
    and does nothing — a confusing result worth warning about rather than
    silently producing. Assume enabled if the file cannot be read: a false
    warning is worse than none. }
  Result := True;
  Settings := AddBackslash(Root) + 'data\nsdata\UserData\UserSettings.json';
  if not FileExists(Settings) then
    Exit;
  if not LoadStringFromFile(Settings, Contents) then
    Exit;
  Marker := Pos('enableModifications', String(Contents));
  if Marker = 0 then
    Exit;
  Tail := Lowercase(Copy(String(Contents), Marker, 40));
  Result := Pos('true', Tail) > 0;
end;

function GetStoredIL2Path(): string;
begin
  Result := '';
  if not RegQueryStringValue(HKA, 'Software\{#MyAppName}', 'IL2Path', Result) then
    Result := '';
end;

function GetIL2Dir(Param: string): string;
begin
  if IL2Page <> nil then
    Result := IL2Page.Values[0]
  else
    Result := GetStoredIL2Path();
end;

procedure PrefillIL2Dir();
var
  Stored, Letters, Base, Candidate: string;
  Parents, Names: TArrayOfString;
  D, P, N: Integer;
begin
  { /IL2DIR="..." on the command line. Lets a silent install be pointed at a
    game folder, and is how the folder logic is tested against layouts that
    are not on this machine. }
  Stored := FindIL2Root(ExpandConstant('{param:IL2DIR}'));
  if Stored <> '' then
  begin
    IL2Page.Values[0] := Stored;
    Exit;
  end;

  Stored := GetStoredIL2Path();
  if (Stored <> '') and LooksLikeIL2Root(Stored) then
  begin
    IL2Page.Values[0] := Stored;
    Exit;
  end;

  { The first release swept six drive letters for a Steam library and stopped
    there, which left every non-Steam owner typing the path by hand — and then
    being told their correct answer was wrong. Sweep the places a manual
    install actually lands as well. Kept in step with locate.py, which does
    the same search when the tracker runs. }
  Letters := 'CDEFGHIJKLMNOPQRSTUVWXYZ';

  { An empty parent means the drive root itself, which is where hawax270's
    copy lives. }
  SetArrayLength(Parents, 6);
  Parents[0] := '';
  Parents[1] := 'Games\';
  Parents[2] := 'Program Files\';
  Parents[3] := 'Program Files (x86)\';
  Parents[4] := 'SteamLibrary\steamapps\common\';
  Parents[5] := 'Program Files (x86)\Steam\steamapps\common\';

  SetArrayLength(Names, 5);
  Names[0] := 'IL2Series';
  Names[1] := 'IL-2 Korea';
  Names[2] := 'IL2Korea';
  Names[3] := 'IL-2 Sturmovik Korea';
  Names[4] := 'Sturmovik Korea';

  for D := 1 to Length(Letters) do
  begin
    Base := Letters[D] + ':\';
    if DirExists(Base) then
      for P := 0 to GetArrayLength(Parents) - 1 do
        for N := 0 to GetArrayLength(Names) - 1 do
        begin
          Candidate := Base + Parents[P] + Names[N];
          { Steam layout, then the direct-sale layout one level deeper. }
          if LooksLikeIL2Root(Candidate) then
          begin
            IL2Page.Values[0] := Candidate;
            Exit;
          end;
          if LooksLikeIL2Root(Candidate + '\game') then
          begin
            IL2Page.Values[0] := Candidate + '\game';
            Exit;
          end;
        end;
  end;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  { The tracker installs into the user's profile without asking for a
    folder, so the last page says where it went. }
  if CurPageID = wpFinished then
  begin
    WizardForm.FinishedLabel.Caption := FmtMessage(CustomMessage('Installed'), [ExpandConstant('{app}'),
      ExpandConstant('{localappdata}\IL2KoreaTracker'), '{#MyAppName}']);
    { The label is sized for the stock text; grow it and move the run box down. }
    WizardForm.FinishedLabel.AdjustHeight();
    WizardForm.RunList.Top := WizardForm.FinishedLabel.Top + WizardForm.FinishedLabel.Height + ScaleY(12);
  end;
end;

procedure InitializeWizard();
begin
  IL2Page := CreateInputDirPage(wpSelectComponents,
    CustomMessage('IL2PageTitle'),
    CustomMessage('IL2PageDescription'),
    CustomMessage('IL2PagePrompt'),
    False, '');
  IL2Page.Add('');
  PrefillIL2Dir();
end;

function GetInstallerLocaleCode(): string;
begin
  if ActiveLanguage = 'german' then Result := 'de'
  else if ActiveLanguage = 'french' then Result := 'fr'
  else if ActiveLanguage = 'spanish' then Result := 'es'
  else if ActiveLanguage = 'russian' then Result := 'ru'
  else if ActiveLanguage = 'chinesesimplified' then Result := 'zh'
  else Result := 'en';
end;

procedure WriteInstallerLocale();
begin
  { The tracker reads this on its very first run, before any settings file
    exists, so the application opens in the language setup was shown in. }
  SaveStringToFile(ExpandConstant('{app}\locale_setting.txt'),
                   GetInstallerLocaleCode(), False);
end;

procedure WriteGameDir();
begin
  { The user has just told setup where the game is. Pass it on, or the tracker
    falls back to searching for itself and a non-standard install is found
    twice by the installer and never by the application. The registry value
    below carries the same answer; this file survives a profile the registry
    write could not reach. }
  SaveStringToFile(ExpandConstant('{app}\game_dir.txt'),
                   GetIL2Dir(''), False);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Root: string;
begin
  Result := True;
  if CurPageID = IL2Page.ID then
  begin
    { Correct a path that points into the installation rather than at it,
      instead of making the user work out what was wrong. }
    Root := FindIL2Root(IL2Page.Values[0]);
    if Root = '' then
    begin
      MsgBox(CustomMessage('InvalidIL2Folder'), mbError, MB_OK);
      Result := False;
      Exit;
    end;
    IL2Page.Values[0] := Root;
    if WizardIsComponentSelected('mod') and
       (not ModificationsEnabled(IL2Page.Values[0])) then
      if MsgBox(CustomMessage('ModsDisabled'), mbConfirmation, MB_YESNO) = IDNO then
        Result := False;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    WriteInstallerLocale();
    WriteGameDir();
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  { The mod's files need no special handling: Inno removes what it installed,
    and with them gone the game falls back to the archives by itself.
    Photographs and settings are different — they live outside both folders,
    they are the user's own, and they outlive the application on purpose. }
  { Never the corrections and backups: they record changes the Career Helper
    made to the game's own career files, and without them a corrected career
    could not be told from an original one, let alone restored. }
  if CurUninstallStep = usUninstall then
    if MsgBox(CustomMessage('RemovePhotosTitle'), mbConfirmation, MB_YESNO) = IDYES then
    begin
      DelTree(ExpandConstant('{localappdata}\IL2KoreaTracker\photos'), True, True, True);
      DelTree(ExpandConstant('{localappdata}\IL2KoreaTracker\assets'), True, True, True);
      DelTree(ExpandConstant('{localappdata}\IL2KoreaTracker\award'), True, True, True);
      DelTree(ExpandConstant('{localappdata}\IL2KoreaTracker\rank'), True, True, True);
      DelTree(ExpandConstant('{localappdata}\IL2KoreaTracker\squadron'), True, True, True);
      DeleteFile(ExpandConstant('{localappdata}\IL2KoreaTracker\settings.json'));
      DeleteFile(ExpandConstant('{localappdata}\IL2KoreaTracker\tracker.log'));
    end;
end;
