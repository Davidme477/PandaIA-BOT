#define MyAppName "PandaIA BOT"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "PandaIA"
#define MyAppExeName "PandaIA.exe"

[Setup]
AppId={{8E012EF9-6A98-4B3B-B83E-805399953D43}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\PandaIA BOT
DefaultGroupName=PandaIA BOT
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\installer_output
OutputBaseFilename=PandaIA-BOT-Setup-{#MyAppVersion}-x64
SetupIconFile=..\..\resources\icons\pandaia.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"; Flags: unchecked

[Files]
Source: "..\..\dist\PandaIA\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\PandaIA BOT"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\PandaIA BOT"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Iniciar PandaIA BOT"; Flags: nowait postinstall skipifsilent

; Los datos de %LOCALAPPDATA%\PandaIA no se incluyen en [UninstallDelete].
; Esto conserva preferencias y credenciales al actualizar o desinstalar.
