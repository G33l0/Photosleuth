; Inno Setup script for PhotoSleuth (features G36 and G37)
;
; Build order:
;   1. pyinstaller packaging/photosleuth.spec --noconfirm --clean
;   2. iscc packaging\installer.iss
;
; Produces dist/installer/PhotoSleuth-<version>-Setup.exe
;
; The installer defaults to a per-user install, so no administrator prompt
; appears; choosing "for all users" elevates only if the user asks for it.

#define AppName        "PhotoSleuth"
#define AppVersion     "1.1.0"
#define AppPublisher   "IamG2"
#define AppURL         "https://github.com/g33l0/photosleuth"
#define AppExeName     "PhotoSleuth.exe"
#define CliExeName     "photosleuth-cli.exe"
#define SourceDir      "..\dist\PhotoSleuth"
#define AssetsDir      "..\photosleuth\assets"

[Setup]
AppId={{8D3F27A1-4C6B-4E0A-9F51-2B7C6E9A1D44}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
AppUpdatesURL={#AppURL}/releases
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
OutputDir=..\dist\installer
OutputBaseFilename={#AppName}-{#AppVersion}-Setup
SetupIconFile={#AssetsDir}\photosleuth.ico
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName} {#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
WizardImageFile={#AssetsDir}\installer_wizard.bmp
WizardSmallImageFile={#AssetsDir}\installer_banner.bmp
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
AppMutex=PhotoSleuthRunningMutex

[Languages]
Name: "english";    MessagesFile: "compiler:Default.isl"
Name: "spanish";    MessagesFile: "compiler:Languages\Spanish.isl"
Name: "french";     MessagesFile: "compiler:Languages\French.isl"
Name: "german";     MessagesFile: "compiler:Languages\German.isl"
Name: "portuguese"; MessagesFile: "compiler:Languages\Portuguese.isl"

[Tasks]
Name: "desktopicon";     Description: "{cm:CreateDesktopIcon}"; \
    GroupDescription: "{cm:AdditionalIcons}"
Name: "explorermenu";    Description: "Add ""Analyze with PhotoSleuth"" to the right-click menu"; \
    GroupDescription: "Windows integration"
Name: "associate";       Description: "Show PhotoSleuth in ""Open with"" for image files"; \
    GroupDescription: "Windows integration"
Name: "addtopath";       Description: "Add the command-line tool to PATH"; \
    GroupDescription: "Windows integration"; Flags: unchecked

[Files]
Source: "{#SourceDir}\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#SourceDir}\*";             DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.md";               DestDir: "{app}"; DestName: "README.md"; Flags: ignoreversion
Source: "..\LICENSE";                 DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}";               Filename: "{app}\{#AppExeName}"
Name: "{group}\{#AppName} (portable data)"; Filename: "{app}\{#AppExeName}"; \
    Comment: "Runs with settings stored next to the program"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}";         Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Registry]
; --- ProgID used by both the "Open with" entry and the context menu ---
Root: HKA; Subkey: "Software\Classes\PhotoSleuth.Image"; \
    ValueType: string; ValueName: ""; ValueData: "Image (PhotoSleuth)"; \
    Flags: uninsdeletekey; Tasks: associate
Root: HKA; Subkey: "Software\Classes\PhotoSleuth.Image\DefaultIcon"; \
    ValueType: string; ValueName: ""; ValueData: "{app}\{#AppExeName},0"; \
    Flags: uninsdeletekey; Tasks: associate
Root: HKA; Subkey: "Software\Classes\PhotoSleuth.Image\shell\open\command"; \
    ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExeName}"" ""%1"""; \
    Flags: uninsdeletekey; Tasks: associate

; --- "Open with" for each image type (the default viewer is left alone) ---
Root: HKA; Subkey: "Software\Classes\.jpg\OpenWithProgids";  ValueType: none; ValueName: "PhotoSleuth.Image"; Flags: uninsdeletevalue; Tasks: associate
Root: HKA; Subkey: "Software\Classes\.jpeg\OpenWithProgids"; ValueType: none; ValueName: "PhotoSleuth.Image"; Flags: uninsdeletevalue; Tasks: associate
Root: HKA; Subkey: "Software\Classes\.png\OpenWithProgids";  ValueType: none; ValueName: "PhotoSleuth.Image"; Flags: uninsdeletevalue; Tasks: associate
Root: HKA; Subkey: "Software\Classes\.tif\OpenWithProgids";  ValueType: none; ValueName: "PhotoSleuth.Image"; Flags: uninsdeletevalue; Tasks: associate
Root: HKA; Subkey: "Software\Classes\.tiff\OpenWithProgids"; ValueType: none; ValueName: "PhotoSleuth.Image"; Flags: uninsdeletevalue; Tasks: associate
Root: HKA; Subkey: "Software\Classes\.bmp\OpenWithProgids";  ValueType: none; ValueName: "PhotoSleuth.Image"; Flags: uninsdeletevalue; Tasks: associate
Root: HKA; Subkey: "Software\Classes\.gif\OpenWithProgids";  ValueType: none; ValueName: "PhotoSleuth.Image"; Flags: uninsdeletevalue; Tasks: associate
Root: HKA; Subkey: "Software\Classes\.webp\OpenWithProgids"; ValueType: none; ValueName: "PhotoSleuth.Image"; Flags: uninsdeletevalue; Tasks: associate
Root: HKA; Subkey: "Software\Classes\.heic\OpenWithProgids"; ValueType: none; ValueName: "PhotoSleuth.Image"; Flags: uninsdeletevalue; Tasks: associate
Root: HKA; Subkey: "Software\Classes\.dng\OpenWithProgids";  ValueType: none; ValueName: "PhotoSleuth.Image"; Flags: uninsdeletevalue; Tasks: associate
Root: HKA; Subkey: "Software\Classes\.cr2\OpenWithProgids";  ValueType: none; ValueName: "PhotoSleuth.Image"; Flags: uninsdeletevalue; Tasks: associate
Root: HKA; Subkey: "Software\Classes\.nef\OpenWithProgids";  ValueType: none; ValueName: "PhotoSleuth.Image"; Flags: uninsdeletevalue; Tasks: associate
Root: HKA; Subkey: "Software\Classes\.arw\OpenWithProgids";  ValueType: none; ValueName: "PhotoSleuth.Image"; Flags: uninsdeletevalue; Tasks: associate

; --- Explorer context menu on files, folders and folder backgrounds ---
Root: HKA; Subkey: "Software\Classes\*\shell\PhotoSleuth"; \
    ValueType: string; ValueName: ""; ValueData: "Analyze with PhotoSleuth"; \
    Flags: uninsdeletekey; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\*\shell\PhotoSleuth"; \
    ValueType: string; ValueName: "Icon"; ValueData: "{app}\{#AppExeName},0"; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\*\shell\PhotoSleuth\command"; \
    ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExeName}"" ""%1"""; \
    Flags: uninsdeletekey; Tasks: explorermenu

Root: HKA; Subkey: "Software\Classes\Directory\shell\PhotoSleuth"; \
    ValueType: string; ValueName: ""; ValueData: "Analyze with PhotoSleuth"; \
    Flags: uninsdeletekey; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\Directory\shell\PhotoSleuth"; \
    ValueType: string; ValueName: "Icon"; ValueData: "{app}\{#AppExeName},0"; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\Directory\shell\PhotoSleuth\command"; \
    ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExeName}"" ""%1"""; \
    Flags: uninsdeletekey; Tasks: explorermenu

Root: HKA; Subkey: "Software\Classes\Directory\Background\shell\PhotoSleuth"; \
    ValueType: string; ValueName: ""; ValueData: "Analyze this folder with PhotoSleuth"; \
    Flags: uninsdeletekey; Tasks: explorermenu
Root: HKA; Subkey: "Software\Classes\Directory\Background\shell\PhotoSleuth\command"; \
    ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExeName}"" ""%V"""; \
    Flags: uninsdeletekey; Tasks: explorermenu

; --- Registered application, so PhotoSleuth appears in Default Apps ---
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExeName}\shell\open\command"; \
    ValueType: string; ValueName: ""; ValueData: """{app}\{#AppExeName}"" ""%1"""; \
    Flags: uninsdeletekey

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Only the program's own cache is removed. Reports the user exported and any
; portable data folder they created are deliberately left in place.
Type: filesandordirs; Name: "{app}\__pycache__"

[Code]
const
  EnvironmentKey = 'Environment';

procedure EnvAddPath(Path: string);
var
  Paths: string;
begin
  if not RegQueryStringValue(HKEY_CURRENT_USER, EnvironmentKey, 'Path', Paths) then
    Paths := '';
  if Pos(';' + Uppercase(Path) + ';', ';' + Uppercase(Paths) + ';') > 0 then
    exit;
  if (Paths <> '') and (Paths[Length(Paths)] <> ';') then
    Paths := Paths + ';';
  RegWriteStringValue(HKEY_CURRENT_USER, EnvironmentKey, 'Path', Paths + Path + ';');
end;

procedure EnvRemovePath(Path: string);
var
  Paths: string;
  P: Integer;
begin
  if not RegQueryStringValue(HKEY_CURRENT_USER, EnvironmentKey, 'Path', Paths) then
    exit;
  P := Pos(';' + Uppercase(Path) + ';', ';' + Uppercase(Paths) + ';');
  if P = 0 then
    exit;
  Delete(Paths, P, Length(Path) + 1);
  RegWriteStringValue(HKEY_CURRENT_USER, EnvironmentKey, 'Path', Paths);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and WizardIsTaskSelected('addtopath') then
    EnvAddPath(ExpandConstant('{app}'));
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    EnvRemovePath(ExpandConstant('{app}'));
end;
