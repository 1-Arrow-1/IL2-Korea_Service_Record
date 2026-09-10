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
; tracker where the player cannot see it — Inno warns about exactly this. The
; override lets Windows offer elevation for the one case that needs it: a game
; folder under Program Files, which the mod has to write into.
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
english.ModOverwriteTitle=The awards mod will replace files in your game folder.
english.ModOverwriteText=A copy of each original is kept alongside it as *.stock, and uninstalling puts them back.%n%nContinue?
english.RemoveModTitle=Remove the awards mod from your game folder?%n%nYour careers, medals already earned and the game itself are untouched either way.%n%nYES restores the original files.%nNO leaves the mod installed.
english.RemovePhotosTitle=Also remove your pilot photographs and settings?%n%nLocation: %%LOCALAPPDATA%%\IL2KoreaTracker%n%nYES deletes them.%nNO keeps them for a future install.
english.CreateDesktopIcon=Create a &desktop icon

german.IL2PageTitle=IL-2 Korea Installation auswählen
german.IL2PageDescription=Der Tracker liest Ihre Karrieren von hier. Der Auszeichnungs-Mod wird, falls gewählt, in diesen Ordner kopiert.
german.IL2PagePrompt=Wählen Sie den Ordner, in dem IL-2 Sturmovik: Korea installiert ist.
german.InvalidIL2Folder=Dieser Ordner scheint keine IL-2 Korea Installation zu sein.%n%nErwartet wurde der Unterordner data\Career.%n%nBitte wählen Sie das Hauptverzeichnis des Spiels.
german.ComponentTracker=Dienstakte (die Tracker-Anwendung)
german.ComponentMod=Auszeichnungs-Mod (ergänzt Orden in der Karriere)
german.ModOverwriteTitle=Der Auszeichnungs-Mod ersetzt Dateien in Ihrem Spielordner.
german.ModOverwriteText=Von jeder Originaldatei wird eine Kopie als *.stock daneben abgelegt; die Deinstallation stellt sie wieder her.%n%nFortfahren?
german.RemoveModTitle=Auszeichnungs-Mod aus dem Spielordner entfernen?%n%nIhre Karrieren, bereits verliehene Orden und das Spiel selbst bleiben in jedem Fall unberührt.%n%nJA stellt die Originaldateien wieder her.%nNEIN belässt den Mod.
german.RemovePhotosTitle=Auch Ihre Pilotenfotos und Einstellungen entfernen?%n%nSpeicherort: %%LOCALAPPDATA%%\IL2KoreaTracker%n%nJA löscht sie.%nNEIN behält sie für eine spätere Installation.
german.CreateDesktopIcon=&Desktop-Symbol erstellen

french.IL2PageTitle=Sélectionnez votre installation d'IL-2 Corée
french.IL2PageDescription=Le carnet lit vos carrières ici. Le mod de décorations, si vous l'installez, est copié dans ce dossier.
french.IL2PagePrompt=Choisissez le dossier où IL-2 Sturmovik: Korea est installé.
french.InvalidIL2Folder=Ce dossier ne semble pas être une installation d'IL-2 Corée.%n%nLe sous-dossier data\Career est attendu.%n%nVeuillez choisir le dossier principal du jeu.
french.ComponentTracker=État de service (l'application)
french.ComponentMod=Mod de décorations (ajoute des décorations à la carrière)
french.ModOverwriteTitle=Le mod de décorations va remplacer des fichiers du jeu.
french.ModOverwriteText=Une copie de chaque original est conservée en *.stock, et la désinstallation les restaure.%n%nContinuer ?
french.RemoveModTitle=Retirer le mod de décorations du dossier du jeu ?%n%nVos carrières, les décorations déjà obtenues et le jeu lui-même ne sont pas touchés.%n%nOUI restaure les fichiers d'origine.%nNON conserve le mod.
french.RemovePhotosTitle=Supprimer aussi vos photographies de pilote et vos réglages ?%n%nEmplacement : %%LOCALAPPDATA%%\IL2KoreaTracker%n%nOUI les supprime.%nNON les conserve.
french.CreateDesktopIcon=Créer une icône sur le &Bureau

spanish.IL2PageTitle=Seleccione su instalación de IL-2 Corea
spanish.IL2PageDescription=La hoja de servicios lee sus carreras de aquí. El mod de condecoraciones, si lo instala, se copia en esta carpeta.
spanish.IL2PagePrompt=Elija la carpeta donde está instalado IL-2 Sturmovik: Korea.
spanish.InvalidIL2Folder=Esa carpeta no parece una instalación de IL-2 Corea.%n%nSe esperaba encontrar data\Career dentro.%n%nElija la carpeta principal del juego.
spanish.ComponentTracker=Hoja de servicios (la aplicación)
spanish.ComponentMod=Mod de condecoraciones (añade condecoraciones a la carrera)
spanish.ModOverwriteTitle=El mod de condecoraciones reemplazará archivos del juego.
spanish.ModOverwriteText=Se conserva una copia de cada original como *.stock, y la desinstalación los restaura.%n%n¿Continuar?
spanish.RemoveModTitle=¿Quitar el mod de condecoraciones de la carpeta del juego?%n%nSus carreras, las condecoraciones ya obtenidas y el juego no se ven afectados.%n%nSÍ restaura los archivos originales.%nNO deja el mod instalado.
spanish.RemovePhotosTitle=¿Eliminar también sus fotografías de piloto y ajustes?%n%nUbicación: %%LOCALAPPDATA%%\IL2KoreaTracker%n%nSÍ los elimina.%nNO los conserva.
spanish.CreateDesktopIcon=Crear un icono en el &escritorio

russian.IL2PageTitle=Выберите установку IL-2 Корея
russian.IL2PageDescription=Послужной список читает ваши карьеры отсюда. Мод наград, если вы его установите, копируется в эту папку.
russian.IL2PagePrompt=Укажите папку, в которую установлена IL-2 Sturmovik: Korea.
russian.InvalidIL2Folder=Эта папка не похожа на установку IL-2 Корея.%n%nОжидалась подпапка data\Career.%n%nВыберите основную папку игры.
russian.ComponentTracker=Послужной список (приложение)
russian.ComponentMod=Мод наград (добавляет награды в карьеру)
russian.ModOverwriteTitle=Мод наград заменит файлы в папке игры.
russian.ModOverwriteText=Копия каждого оригинала сохраняется рядом как *.stock, удаление вернёт их на место.%n%nПродолжить?
russian.RemoveModTitle=Удалить мод наград из папки игры?%n%nВаши карьеры, уже полученные награды и сама игра не пострадают.%n%nДА восстановит исходные файлы.%nНЕТ оставит мод.
russian.RemovePhotosTitle=Удалить также фотографии лётчиков и настройки?%n%nРасположение: %%LOCALAPPDATA%%\IL2KoreaTracker%n%nДА удалит их.%nНЕТ сохранит.
russian.CreateDesktopIcon=Создать значок на &рабочем столе

chinesesimplified.IL2PageTitle=选择您的 IL-2 朝鲜 安装位置
chinesesimplified.IL2PageDescription=服役档案从此处读取您的生涯。若选择安装勋章模组，也将复制到此文件夹。
chinesesimplified.IL2PagePrompt=请选择 IL-2 Sturmovik: Korea 的安装文件夹。
chinesesimplified.InvalidIL2Folder=该文件夹似乎不是 IL-2 朝鲜 的安装位置。%n%n应包含 data\Career 子文件夹。%n%n请选择游戏主文件夹。
chinesesimplified.ComponentTracker=服役档案（主程序）
chinesesimplified.ComponentMod=勋章模组（为生涯增加勋章）
chinesesimplified.ModOverwriteTitle=勋章模组将替换游戏文件夹中的文件。
chinesesimplified.ModOverwriteText=每个原始文件都会以 *.stock 保留副本，卸载时将还原。%n%n是否继续？
chinesesimplified.RemoveModTitle=从游戏文件夹中移除勋章模组？%n%n您的生涯、已获得的勋章以及游戏本身均不受影响。%n%n是：还原原始文件。%n否：保留模组。
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
; These are modified game files and only take effect as loose files, which the
; engine (and the tracker) prefer over the archive copy.
Source: "payload\mod\data\*"; DestDir: "{code:GetIL2Dir}\data"; Components: mod; \
    Flags: ignoreversion recursesubdirs createallsubdirs uninsremovereadonly

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"

[Registry]
; The uninstaller needs the game folder to put the stock files back, and it
; cannot ask the user again at that point.
Root: HKA; Subkey: "Software\{#MyAppName}"; ValueType: string; \
    ValueName: "IL2Path"; ValueData: "{code:GetIL2Dir}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\{#MyAppName}"; ValueType: string; \
    ValueName: "ModInstalled"; ValueData: "{code:GetModFlag}"; Flags: uninsdeletekey

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

function GetModFlag(Param: string): string;
begin
  if WizardIsComponentSelected('mod') then Result := '1' else Result := '0';
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
  { Same drive sweep the tracker itself does, so the common case needs no
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

function BackupName(const FileName: string): string;
begin
  Result := FileName + '.stock';
end;

procedure BackupOriginal(const FileName: string);
begin
  { Only ever taken once. A second install must not overwrite the stock copy
    with the modded one already sitting there. }
  if FileExists(FileName) and (not FileExists(BackupName(FileName))) then
    CopyFile(FileName, BackupName(FileName), False);
end;

procedure BackupModTargets(const Root: string);
var
  Data: string;
  Awards: string;
  Langs: TArrayOfString;
  I: Integer;
begin
  Data := AddBackslash(Root) + 'data\';
  BackupOriginal(Data + 'scg\2\awards.cfg');
  BackupOriginal(Data + 'nsdata\assets\images\awards.xaml');
  BackupOriginal(Data + 'nsdata\assets\images\awards6xx.dds');
  BackupOriginal(Data + 'nsdata\assets\images\awards6xx2.dds');
  Awards := Data + 'nsdata\assets\locale\awards.locale=';
  Langs := ['chs', 'eng', 'fra', 'ger', 'rus', 'spa'];
  for I := 0 to GetArrayLength(Langs) - 1 do
    BackupOriginal(Awards + Langs[I] + '.json');
end;

procedure RestoreOriginal(const FileName: string);
begin
  if FileExists(BackupName(FileName)) then
  begin
    DeleteFile(FileName);
    RenameFile(BackupName(FileName), FileName);
  end
  else
    { No stock copy means the game had no loose file here before the mod, so
      deleting ours returns the engine to the archive copy. }
    DeleteFile(FileName);
end;

procedure RestoreModTargets(const Root: string);
var
  Data: string;
  Awards: string;
  Langs: TArrayOfString;
  Ids: TArrayOfString;
  I, J: Integer;
begin
  Data := AddBackslash(Root) + 'data\';
  RestoreOriginal(Data + 'scg\2\awards.cfg');
  RestoreOriginal(Data + 'nsdata\assets\images\awards.xaml');
  RestoreOriginal(Data + 'nsdata\assets\images\awards6xx.dds');
  RestoreOriginal(Data + 'nsdata\assets\images\awards6xx2.dds');
  Langs := ['chs', 'eng', 'fra', 'ger', 'rus', 'spa'];
  Awards := Data + 'nsdata\assets\locale\awards.locale=';
  for I := 0 to GetArrayLength(Langs) - 1 do
    RestoreOriginal(Awards + Langs[I] + '.json');
  { The description texts are additions, not replacements — nothing to restore. }
  Ids := ['601027', '601040', '601041'];
  for I := 0 to GetArrayLength(Ids) - 1 do
    for J := 0 to GetArrayLength(Langs) - 1 do
      DeleteFile(Data + 'nsdata\assets\awards\6xx\' + Ids[I] + '.locale=' +
                 Langs[J] + '.txt');
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
    if WizardIsComponentSelected('mod') then
      if MsgBox(CustomMessage('ModOverwriteTitle') + #13#10#13#10 +
                CustomMessage('ModOverwriteText'),
                mbConfirmation, MB_YESNO) = IDNO then
        Result := False;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
  begin
    if WizardIsComponentSelected('mod') then
      BackupModTargets(GetIL2Dir(''));
  end
  else if CurStep = ssPostInstall then
    WriteInstallerLocale();
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Root: string;
  ModFlag: string;
begin
  if CurUninstallStep <> usUninstall then
    Exit;

  Root := GetStoredIL2Path();
  if not RegQueryStringValue(HKA, 'Software\{#MyAppName}', 'ModInstalled', ModFlag) then
    ModFlag := '0';

  if (ModFlag = '1') and (Root <> '') and LooksLikeIL2Root(Root) then
    if MsgBox(CustomMessage('RemoveModTitle'), mbConfirmation, MB_YESNO) = IDYES then
      RestoreModTargets(Root);

  { Photographs and settings live outside both folders and outlive the app on
    purpose, so removing them is always a separate, explicit answer. }
  if MsgBox(CustomMessage('RemovePhotosTitle'), mbConfirmation, MB_YESNO) = IDYES then
    DelTree(ExpandConstant('{localappdata}\IL2KoreaTracker'), True, True, True);
end;
