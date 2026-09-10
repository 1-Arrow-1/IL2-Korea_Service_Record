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
#define MyAppVersion "1.0.0"
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
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "french"; MessagesFile: "compiler:Languages\French.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[CustomMessages]
english.IL2PageTitle=Select your IL-2 Korea installation
english.IL2PageDescription=The tracker reads your careers from here. The awards mod, if you install it, is copied into this folder.
english.IL2PagePrompt=Choose the folder IL-2 Sturmovik: Korea is installed in.
english.InvalidIL2Folder=That folder does not look like an IL-2 Korea installation.%n%nExpected to find data\Career inside it.%n%nPlease choose the game's main folder.
english.ComponentTracker=Service Record (the tracker application)
english.ComponentMod=Awards mod (adds decorations to the career)
english.ModsDisabled=Modifications are currently switched off in IL-2 Korea.%n%nThe awards mod will be installed, but the game will ignore it until you turn modifications on:%n%n    Settings  ->  General  ->  Enable modifications%n%nInstall it anyway?
english.RemovePhotosTitle=Also remove your pilot photographs and settings?%n%nLocation: %%LOCALAPPDATA%%\IL2KoreaTracker%n%nYES deletes them.%nNO keeps them for a future install.
english.CreateDesktopIcon=Create a &desktop icon

german.IL2PageTitle=IL-2 Korea Installation auswählen
german.IL2PageDescription=Der Tracker liest Ihre Karrieren von hier. Der Auszeichnungs-Mod wird, falls gewählt, in diesen Ordner kopiert.
german.IL2PagePrompt=Wählen Sie den Ordner, in dem IL-2 Sturmovik: Korea installiert ist.
german.InvalidIL2Folder=Dieser Ordner scheint keine IL-2 Korea Installation zu sein.%n%nErwartet wurde der Unterordner data\Career.%n%nBitte wählen Sie das Hauptverzeichnis des Spiels.
german.ComponentTracker=Dienstakte (die Tracker-Anwendung)
german.ComponentMod=Auszeichnungs-Mod (ergänzt Orden in der Karriere)
german.ModsDisabled=Modifikationen sind in IL-2 Korea derzeit ausgeschaltet.%n%nDer Auszeichnungs-Mod wird installiert, das Spiel ignoriert ihn jedoch, bis Sie Modifikationen einschalten:%n%n    Einstellungen  ->  Allgemein  ->  Modifikationen aktivieren%n%nTrotzdem installieren?
german.RemovePhotosTitle=Auch Ihre Pilotenfotos und Einstellungen entfernen?%n%nSpeicherort: %%LOCALAPPDATA%%\IL2KoreaTracker%n%nJA löscht sie.%nNEIN behält sie für eine spätere Installation.
german.CreateDesktopIcon=&Desktop-Symbol erstellen

french.IL2PageTitle=Sélectionnez votre installation d'IL-2 Corée
french.IL2PageDescription=Le carnet lit vos carrières ici. Le mod de décorations, si vous l'installez, est copié dans ce dossier.
french.IL2PagePrompt=Choisissez le dossier où IL-2 Sturmovik: Korea est installé.
french.InvalidIL2Folder=Ce dossier ne semble pas être une installation d'IL-2 Corée.%n%nLe sous-dossier data\Career est attendu.%n%nVeuillez choisir le dossier principal du jeu.
french.ComponentTracker=État de service (l'application)
french.ComponentMod=Mod de décorations (ajoute des décorations à la carrière)
french.ModsDisabled=Les modifications sont actuellement désactivées dans IL-2 Corée.%n%nLe mod sera installé, mais le jeu l'ignorera tant que vous n'aurez pas activé les modifications :%n%n    Paramètres  ->  Général  ->  Activer les modifications%n%nInstaller quand même ?
french.RemovePhotosTitle=Supprimer aussi vos photographies de pilote et vos réglages ?%n%nEmplacement : %%LOCALAPPDATA%%\IL2KoreaTracker%n%nOUI les supprime.%nNON les conserve.
french.CreateDesktopIcon=Créer une icône sur le &Bureau

spanish.IL2PageTitle=Seleccione su instalación de IL-2 Corea
spanish.IL2PageDescription=La hoja de servicios lee sus carreras de aquí. El mod de condecoraciones, si lo instala, se copia en esta carpeta.
spanish.IL2PagePrompt=Elija la carpeta donde está instalado IL-2 Sturmovik: Korea.
spanish.InvalidIL2Folder=Esa carpeta no parece una instalación de IL-2 Corea.%n%nSe esperaba encontrar data\Career dentro.%n%nElija la carpeta principal del juego.
spanish.ComponentTracker=Hoja de servicios (la aplicación)
spanish.ComponentMod=Mod de condecoraciones (añade condecoraciones a la carrera)
spanish.ModsDisabled=Las modificaciones están desactivadas en IL-2 Corea.%n%nEl mod se instalará, pero el juego lo ignorará hasta que active las modificaciones:%n%n    Ajustes  ->  General  ->  Activar modificaciones%n%n¿Instalar de todos modos?
spanish.RemovePhotosTitle=¿Eliminar también sus fotografías de piloto y ajustes?%n%nUbicación: %%LOCALAPPDATA%%\IL2KoreaTracker%n%nSÍ los elimina.%nNO los conserva.
spanish.CreateDesktopIcon=Crear un icono en el &escritorio

russian.IL2PageTitle=Выберите установку IL-2 Корея
russian.IL2PageDescription=Послужной список читает ваши карьеры отсюда. Мод наград, если вы его установите, копируется в эту папку.
russian.IL2PagePrompt=Укажите папку, в которую установлена IL-2 Sturmovik: Korea.
russian.InvalidIL2Folder=Эта папка не похожа на установку IL-2 Корея.%n%nОжидалась подпапка data\Career.%n%nВыберите основную папку игры.
russian.ComponentTracker=Послужной список (приложение)
russian.ComponentMod=Мод наград (добавляет награды в карьеру)
russian.ModsDisabled=Модификации в IL-2 Корея сейчас отключены.%n%nМод будет установлен, но игра не увидит его, пока вы не включите модификации:%n%n    Настройки  ->  Общие  ->  Включить модификации%n%nВсё равно установить?
russian.RemovePhotosTitle=Удалить также фотографии лётчиков и настройки?%n%nРасположение: %%LOCALAPPDATA%%\IL2KoreaTracker%n%nДА удалит их.%nНЕТ сохранит.
russian.CreateDesktopIcon=Создать значок на &рабочем столе

chinesesimplified.IL2PageTitle=选择您的 IL-2 朝鲜 安装位置
chinesesimplified.IL2PageDescription=服役档案从此处读取您的生涯。若选择安装勋章模组，也将复制到此文件夹。
chinesesimplified.IL2PagePrompt=请选择 IL-2 Sturmovik: Korea 的安装文件夹。
chinesesimplified.InvalidIL2Folder=该文件夹似乎不是 IL-2 朝鲜 的安装位置。%n%n应包含 data\Career 子文件夹。%n%n请选择游戏主文件夹。
chinesesimplified.ComponentTracker=服役档案（主程序）
chinesesimplified.ComponentMod=勋章模组（为生涯增加勋章）
chinesesimplified.ModsDisabled=IL-2 朝鲜 当前已关闭模组功能。%n%n模组仍会安装，但在您启用模组之前游戏不会读取它：%n%n    设置  ->  常规  ->  启用模组%n%n仍要安装吗？
chinesesimplified.RemovePhotosTitle=同时删除您的飞行员照片与设置？%n%n位置：%%LOCALAPPDATA%%\IL2KoreaTracker%n%n是：删除。%n否：保留以备将来安装。
chinesesimplified.CreateDesktopIcon=创建桌面图标(&D)

[Types]
Name: "full"; Description: "{cm:ComponentTracker} + {cm:ComponentMod}"
Name: "trackeronly"; Description: "{cm:ComponentTracker}"
Name: "custom"; Description: "Custom"; Flags: iscustom

[Components]
Name: "tracker"; Description: "{cm:ComponentTracker}"; Types: full trackeronly custom; Flags: fixed
Name: "mod"; Description: "{cm:ComponentMod}"; Types: full

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; --- The tracker. Self-contained; ships no game data of any kind. ---
Source: "payload\tracker\*"; DestDir: "{app}"; Components: tracker; \
    Flags: ignoreversion recursesubdirs createallsubdirs

; --- The awards mod, into the folder chosen on the custom page. ---
; Additions to data\, which the game reads in preference to the archives while
; modifications are enabled. Inno records each one and removes it on uninstall,
; which is the whole of the cleanup: with the files gone the game finds nothing
; loose and reads the archive again.
Source: "payload\mod\data\*"; DestDir: "{code:GetIL2Dir}\data"; Components: mod; \
    Flags: ignoreversion recursesubdirs createallsubdirs uninsremovereadonly

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"

[Registry]
; Remembered so a reinstall prefills the same folder.
Root: HKA; Subkey: "Software\{#MyAppName}"; ValueType: string; \
    ValueName: "IL2Path"; ValueData: "{code:GetIL2Dir}"; Flags: uninsdeletekey

[UninstallDelete]
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
begin
  { data\Career is where the game keeps the .db files the tracker reads, and it
    exists in every installation that has ever been played. }
  Result := DirExists(AddBackslash(Dir) + 'data\Career');
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
  Stored: string;
  Drives: string;
  I: Integer;
  Candidate: string;
begin
  Stored := GetStoredIL2Path();
  if (Stored <> '') and LooksLikeIL2Root(Stored) then
  begin
    IL2Page.Values[0] := Stored;
    Exit;
  end;
  { The same drive sweep the tracker itself does, so the common case needs no
    typing: a Steam library on any of the usual letters. }
  Drives := 'CDEFGH';
  for I := 1 to Length(Drives) do
  begin
    Candidate := Drives[I] + ':\SteamLibrary\steamapps\common\IL2Series';
    if LooksLikeIL2Root(Candidate) then
    begin
      IL2Page.Values[0] := Candidate;
      Exit;
    end;
    Candidate := Drives[I] + ':\Program Files (x86)\Steam\steamapps\common\IL2Series';
    if LooksLikeIL2Root(Candidate) then
    begin
      IL2Page.Values[0] := Candidate;
      Exit;
    end;
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

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = IL2Page.ID then
  begin
    if not LooksLikeIL2Root(IL2Page.Values[0]) then
    begin
      MsgBox(CustomMessage('InvalidIL2Folder'), mbError, MB_OK);
      Result := False;
      Exit;
    end;
    if WizardIsComponentSelected('mod') and
       (not ModificationsEnabled(IL2Page.Values[0])) then
      if MsgBox(CustomMessage('ModsDisabled'), mbConfirmation, MB_YESNO) = IDNO then
        Result := False;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    WriteInstallerLocale();
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  { The mod's files need no special handling: Inno removes what it installed,
    and with them gone the game falls back to the archives by itself.
    Photographs and settings are different — they live outside both folders,
    they are the user's own, and they outlive the application on purpose. }
  if CurUninstallStep = usUninstall then
    if MsgBox(CustomMessage('RemovePhotosTitle'), mbConfirmation, MB_YESNO) = IDYES then
      DelTree(ExpandConstant('{localappdata}\IL2KoreaTracker'), True, True, True);
end;
